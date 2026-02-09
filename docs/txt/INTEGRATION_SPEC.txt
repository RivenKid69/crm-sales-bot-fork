# Документация по интеграции CRM Sales Bot (AI‑сервис)

> Документ предназначен для аналитика, составляющего ТЗ на интеграцию AI‑сервиса
> в мессенджер-платформу (аналог Wazzup).
>
> **Принцип:** AI‑сервис — **stateless**. Никаких локальных сессий, файлов, кешей.
> Всё состояние передаётся в аргументах запроса и возвращается в ответе.

---

## 0. Глоссарий терминов

| Термин | Определение |
|---|---|
| **Snapshot** | Полный сериализованный слепок состояния бота на конкретный момент времени. Содержит состояние конечного автомата (FSM), собранные данные клиента, историю интентов, lead score, уровень фрустрации, контекстное окно и метрики. Используется для возобновления диалога с того места, где он был прерван. Хранится внешней системой в MongoDB. |
| **Config** | Конфигурация поведения бота: настройки sales flow, пороги, feature flags, промпт‑шаблоны, таксономия интентов, лимиты диалога, параметры lead scoring и т.д. Хранится в YAML‑файлах на стороне AI‑сервиса. В запросе указывается `config_name` — имя конфигурации для загрузки. |
| **Flow** | Методология продаж (например, SPIN Selling, BANT, MEDDIC). Определяет последовательность фаз, состояний, правил перехода и шаблонов промптов. Всего 21 flow. |
| **Phase** | Этап внутри flow. Например, в SPIN Selling фазы: Situation → Problem → Implication → Need-Payoff → Presentation → Close. Каждой фазе соответствует одно или несколько состояний FSM. |
| **State (состояние FSM)** | Конкретный узел в конечном автомате бота. Определяет, какое действие бот выполняет и куда может перейти далее. Примеры: `greeting`, `spin_situation`, `spin_problem`, `close`. |
| **Intent (намерение)** | Классифицированное намерение пользователя. Бот определяет intent на каждом ходе (247 интентов в 34 категориях). Примеры: `greeting`, `price_question`, `demo_request`, `objection_price`. |
| **Turn (ход)** | Одна пара «сообщение пользователя → ответ бота». Каждый turn нумеруется и порождает decision trace. |
| **Decision Trace** | Полная трассировка решений бота на каждом turn: какой intent определён, с какой уверенностью, какое действие выбрано, как изменился lead score, сработал ли guard и т.д. Возвращается при `enable_tracing=True` (обязателен для API-обёртки). |
| **Lead Score** | Оценка «прогретости» лида от 0 до 100. Рассчитывается динамически по сигналам (контакт дан, демо запрошено, возражение и т.д.). Определяет temperature: cold (0–29), warm (30–49), hot (50–69), very_hot (70–100). |
| **Guard** | Защитный механизм диалога. Отслеживает зацикливание, фрустрацию, стагнацию и решает, когда нужно предложить варианты (tier 2), пропустить фазу (tier 3) или завершить мягко (soft close). |
| **Fallback** | Стратегия на случай, когда бот не может корректно обработать сообщение. 4 уровня: tier 1 (перефразировать), tier 2 (предложить варианты), tier 3 (перейти к следующей фазе), soft close (мягкое завершение). |
| **Objection (возражение)** | Возражение клиента. 8 типов: PRICE, COMPETITOR, NO_TIME, THINK, NO_NEED, TRUST, TIMING, COMPLEXITY. Обрабатывается фреймворками 4P's (рациональный) и 3F's (эмоциональный). |
| **CTA (Call-to-Action)** | Призыв к целевому действию (демо, контакт, обратный звонок), который бот добавляет к ответу при высокой готовности клиента. |
| **Disambiguation** | Уточнение намерения пользователя. Если классификатор не уверен, бот предлагает варианты (например: «Вы спрашиваете о цене или о функциях?»). |
| **Escalation** | Передача диалога оператору. Может быть инициирована ботом (фрустрация, sensitive topics, явный запрос) или оператором (перехват). |
| **Collected Data** | Структурированные данные, извлечённые из диалога: размер компании, текущие инструменты, болевые точки, бюджет, контакты и т.д. |
| **Context Window** | Скользящее окно последних turn-ов. Используется для обнаружения паттернов (зацикливание, осцилляция) и формирования контекста для LLM. |
| **History Compact** | Сжатое резюме диалога, созданное LLM при закрытии сессии. Содержит: summary, key facts, возражения, решения, открытые вопросы, следующие шаги. |
| **Tenant** | Клиент‑арендатор платформы. Идентифицируется по `client_id`. Каждый tenant может иметь свой config, flow и набор диалогов. |
| **Reranker** | Модель для пере‑ранжирования результатов поиска по базе знаний. Используется BAAI/bge-reranker-v2-m3 для повышения точности ответов. |
| **Cascade Classifier** | Многоуровневый классификатор интентов: rule-based → embedding → LLM. Каждый уровень подключается, если предыдущий не дал уверенного результата. |

---

## 1. Общее описание системы

**CRM Sales Bot** — интеллектуальный B2B-чат-бот для продажи CRM-системы Wipon.
Бот ведёт диалог по методологии SPIN Selling, квалифицирует лидов, обрабатывает
возражения, отвечает на вопросы из базы знаний и доводит клиента до целевого действия
(демо, контакт, обратный звонок).

### 1.1 Ключевые возможности

| Возможность | Описание |
|---|---|
| SPIN Selling | Поэтапный диалог: Ситуация → Проблема → Следствия → Выгода → Презентация → Закрытие |
| 21 sales flow | Переключаемые методологии продаж (SPIN, BANT, MEDDIC, AIDA, NEAT и др.) |
| 247 интентов | Классификация намерений пользователя в 34 категориях |
| База знаний | 1 969 секций в 17 категориях (цены, продукты, оборудование, интеграции и т.д.) |
| Обработка возражений | 8 типов возражений, 120+ паттернов, фреймворки 4P's и 3F's |
| Lead scoring | Динамическая оценка лида (0–100) с температурой (cold/warm/hot/very_hot) |
| Анализ тона | 3-уровневый каскад: regex → FRIDA (semantic) → LLM; фрустрация 0–10 |
| Защитные механизмы | Конверсационный guard, stall detection, phase exhaustion, fallback 4 уровней |
| Decision tracing | Полная трассировка всех решений на каждом ходе (обязательная) |

### 1.2 Технологический стек

| Компонент | Технология | Версия |
|---|---|---|
| Язык | Python | 3.10+ |
| LLM | Qwen3 14B через Ollama | localhost:11434 |
| Embeddings | ai-forever/FRIDA | Sentence Transformers ≥2.2.0 |
| Reranker | BAAI/bge-reranker-v2-m3 | — |
| Морфология | pymorphy3 | ≥2.0.0 |
| HTTP-клиент | requests | ≥2.28.0 |
| Сериализация конфигов | PyYAML | ≥6.0 |
| Numpy | numpy | ≥1.24.0 |
| Async HTTP | aiohttp | ≥3.8.0 |
| Тесты | pytest | ≥7.0.0 |
| Линтер | ruff | ≥0.1.0 |
| Типизация | mypy | ≥1.0.0 |
| **Для API-обёртки** | FastAPI ≥0.110.0, Uvicorn ≥0.29.0, Pydantic ≥2.0.0 | *Не в зависимостях ядра — нужно добавить при создании REST API* |
| Размер кодовой базы | ~80 000 строк кода | 160+ модулей (src/) |
| Тесты | 234 файла | 9 099 тестов |

### 1.3 Архитектура AI‑сервиса

AI‑сервис работает **исключительно в режиме «запрос — ответ»**:

1. Внешняя система присылает HTTP‑запрос с сообщением пользователя, snapshot (если есть), `config_name` и историей
2. Сервис обрабатывает сообщение, формирует ответ и обновлённый snapshot
3. Сервис возвращает JSON‑ответ со строгой схемой
4. Сервис **не хранит** никакого состояния между запросами

```
Внешняя система                    AI‑сервис (stateless)
     │                                    │
     │  POST /api/v1/process              │
     │  { message, snapshot, config_name, │
     │    history_tail, client_id, ... }   │
     │ ──────────────────────────────────▶ │
     │                                    │  → Восстановить бота из snapshot
     │                                    │  → Обработать сообщение
     │                                    │  → Сформировать ответ
     │  { response, snapshot, trace, ... } │
     │ ◀────────────────────────────────── │
     │                                    │
     │  Сохранить snapshot в MongoDB       │
     │  Отправить response клиенту         │
```

Чего **нет** в AI‑сервисе (делает внешняя система):
- Кеша сессий и SessionManager — **убран**
- Локальных файловых lock-ов — **убраны**
- Прямого подключения к БД
- Локального хранения snapshot-ов и истории
- Подключения к мессенджерам

---

## 2. Требования к интеграции

### 2.1 Разделение ответственности

**Внешняя система (мессенджер-платформа):**
- принимает входящие сообщения из каналов (WhatsApp, Telegram и др.)
- определяет `client_id`, `session_id`
- хранит snapshot-ы и историю сообщений в **MongoDB**
- управляет сессиями и их жизненным циклом
- обеспечивает последовательную обработку сообщений внутри одной сессии
- обеспечивает дедупликацию входящих webhook/message событий
- при каждом запросе к AI‑сервису передаёт snapshot, `config_name` и хвост истории
- принимает ответ и сохраняет обновлённый snapshot
- роутит сообщения между ботом и оператором

**AI‑сервис (ядро бота):**
- принимает HTTP-запрос
- восстанавливает состояние бота из переданного snapshot
- обрабатывает сообщение и формирует ответ
- возвращает JSON с ответом, обновлённым snapshot и decision trace
- **не хранит** никакого состояния между запросами

### 2.2 Идентификация и изоляция

Минимальный набор идентификаторов:
- `client_id` — идентификатор клиента/тенанта (обязателен для изоляции)
- `session_id` — идентификатор диалога (conversation/chat)

Рекомендуется делать `session_id` глобально уникальным между tenant-ами
(например, `"{client_id}::{external_chat_id}"`), чтобы исключить коллизии.

`client_id` **всегда пишется внутрь snapshot**.
При восстановлении, если `snapshot.client_id != expected client_id`, snapshot игнорируется.

### 2.3 Конкуррентность

Даже в stateless‑архитектуре возможны гонки, если два сообщения из одного чата
придут одновременно. Внешняя система должна обеспечить **последовательную обработку
сообщений внутри одной `session_id`** (очередь или distributed lock на уровне
внешней системы, например через Redis или MongoDB advisory lock).

### 2.4 Хостинг и инфраструктура (ориентир)

| Параметр | Значение |
|---|---|
| LLM | Qwen3 14B через Ollama (требуется GPU‑сервер, ~9.3 GB VRAM) |
| Embedding‑модели | Локальные, загружаются при старте AI‑сервиса (~500 MB) |
| AI‑сервис | Stateless, горизонтально масштабируется |

### 2.5 Логирование

Structured‑логи идут в stdout (JSON/Readable через `LOG_FORMAT`).
При интеграции можно забирать логи через stdout collector.

### 2.6 Админ‑панель и оператор

Админ‑панель и операторские сценарии описаны ниже (разделы 6–7).
Они не обязательны для запуска базовой интеграции.

---

## 3. API‑контракт (REST)

### 3.1 Предполагаемые эндпоинты

#### `POST /api/v1/process` — обработка сообщения

Основной эндпоинт. Принимает сообщение пользователя, возвращает ответ бота.

**Request:**

```json
{
  "client_id": "tenant-42",
  "session_id": "chat-123",
  "flow_name": "spin_selling",
  "config_name": "tenant_alpha",
  "user_message": "А сколько стоит ваша система?",

  "snapshot": { ... },

  "history_tail": [
    {"user": "Привет", "bot": "Добрый день! Расскажите о вашей компании."},
    {"user": "У нас магазин, 50 сотрудников", "bot": "Какую систему учёта используете?"}
  ]
}
```

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `client_id` | `string` | Да | Идентификатор тенанта |
| `session_id` | `string` | Да | Идентификатор диалога |
| `flow_name` | `string` | Да | Имя sales flow (`spin_selling`, `bant`, ...) |
| `config_name` | `string` | Нет | Имя конфигурации (YAML). Если не указан — используется `default` |
| `user_message` | `string` | Да | Текст сообщения пользователя |
| `snapshot` | `object \| null` | Нет | Предыдущий snapshot. `null` для нового диалога |
| `history_tail` | `array` | Нет | Последние N сообщений в формате `[{"user": "...", "bot": "..."}]`. По умолчанию — последние 4 хода |

> **Про config (design decision):**
>
> Конфигурация (методология продаж, тональность, лимиты, feature flags, таксономия
> интентов, шаблоны промптов, lead scoring сигналы) хранится в **YAML‑файлах на
> стороне AI‑сервиса**. Внешняя система указывает `config_name` — имя named-конфига.
> Если named-конфиг не найден, сервис загрузит default-конфиг.
>
> **Почему не config injection (JSON в запросе):**
> Конфигурация бота — это не один файл, а **набор из 5+ связанных YAML-файлов**
> (constants, flow, knowledge base, prompt templates, intent taxonomy), суммарно
> десятки тысяч строк. Все компоненты ядра (StateMachine, Classifier, Guard,
> LeadScorer, FallbackHandler, ResponseGenerator) получают `LoadedConfig` при
> инициализации и используют его на всех этапах обработки. Передача всей конфигурации
> JSON-объектом в каждом запросе нецелесообразна по объёму и потребует глубокого
> рефакторинга ядра.
>
> **Подход:** каждый tenant получает свою директорию конфигов на AI‑сервисе
> (`config/tenants/{config_name}/`). Управление конфигами — через админ-панель
> или CI/CD деплой. Проверку существования нужного конфига рекомендуется делать
> заранее через `GET /api/v1/configs`.
>
> **Динамическая конфигурация (реализовано):** для изменения лимитов, порогов
> и поведения без редеплоя реализован `POST /api/v1/configs/{name}/override` —
> горячее обновление отдельных параметров `constants` в рантайме (см. описание
> эндпоинта ниже). Структурные ключи (intents, states, policy) требуют редеплоя.

**Response — прямой вывод `process()` (`src/bot.py`):**

```json
{
  "response": "Стоимость зависит от тарифа. Для компании в 50 сотрудников...",
  "is_final": false,

  "intent": "price_question",
  "action": "answer_with_pricing",
  "state": "spin_situation",
  "spin_phase": "situation",
  "visited_states": ["greeting", "spin_situation"],
  "initial_state": "greeting",

  "fallback_used": false,
  "fallback_tier": null,
  "tone": "neutral",
  "frustration_level": 1,
  "lead_score": 20,
  "objection_detected": false,
  "options": null,
  "cta_added": false,
  "cta_text": null,
  "decision_trace": { ... }
}
```

| Поле | Тип | Описание |
|---|---|---|
| `response` | `string` | Текст ответа — отправить клиенту |
| `is_final` | `boolean` | `true` = диалог завершён, больше не роутить в бота |
| `intent` | `string` | Определённый интент пользователя |
| `action` | `string` | Выбранное действие бота |
| `state` | `string` | Состояние FSM **после** обработки (next_state) |
| `spin_phase` | `string \| null` | Текущая фаза flow (напр. `"situation"`, `"problem"`) |
| `visited_states` | `array` | Все состояния, посещённые на этом ходе (для покрытия фаз при skip) |
| `initial_state` | `string` | Состояние FSM **до** обработки |
| `fallback_used` | `boolean` | Был ли использован fallback |
| `fallback_tier` | `string \| null` | Уровень fallback: `"fallback_tier_1"`, `"fallback_tier_2"`, `"fallback_tier_3"`, `"soft_close"` или `null` |
| `tone` | `string` | Определённый тон пользователя |
| `frustration_level` | `integer` | Уровень фрустрации (0–10) |
| `lead_score` | `integer \| null` | Текущий lead score (0–100). `null` если feature flag `lead_scoring` отключен |
| `objection_detected` | `boolean` | Было ли обнаружено возражение |
| `options` | `array \| null` | Варианты для пользователя (при guard/fallback) или `null` |
| `cta_added` | `boolean` | Добавлен ли CTA к ответу |
| `cta_text` | `string \| null` | Текст CTA или `null` |
| `decision_trace` | `object \| null` | Трассировка решений (см. раздел 5). **`null` если `enable_tracing=False`** (см. примечание ниже) |

> **Поля, которых НЕТ в `process()` — добавляются API-обёрткой:**
>
> | Поле | Источник | Описание |
> |---|---|---|
> | `snapshot` | `bot.to_snapshot()` | Обновлённый snapshot (вызвать **после** `process()`, сохранить в MongoDB) |
> | `confidence` | `decision_trace.classification.confidence` | Уверенность классификации (0.0–1.0). Извлечь из `decision_trace` |
> | `lead_temperature` | Вычислить из `lead_score` | `cold` (0–29), `warm` (30–49), `hot` (50–69), `very_hot` (70–100) |
> | `collected_data` | `snapshot.state_machine.collected_data` | Данные клиента. Извлечь из snapshot |
>
> API-обёртка **обязана** создавать `SalesBot` с `enable_tracing=True`, чтобы `decision_trace`
> возвращался в каждом ответе. По умолчанию в конструкторе `SalesBot` `enable_tracing=False`,
> и тогда `decision_trace` будет `None`.

---

#### `POST /api/v1/restore` — восстановление бота из snapshot (опционально)

Позволяет валидировать snapshot и получить текущее состояние бота без обработки нового сообщения. Полезно при возврате от оператора.

**Request:**

```json
{
  "client_id": "tenant-42",
  "session_id": "chat-123",
  "flow_name": "spin_selling",
  "config_name": "tenant_alpha",
  "snapshot": { ... },
  "history_tail": [...]
}
```

**Response:**

```json
{
  "valid": true,
  "state": "spin_problem",
  "spin_phase": "problem",
  "lead_score": 35,
  "lead_temperature": "warm",
  "turn_count": 5,
  "collected_data": {"company_size": "50", "current_tools": "Excel"}
}
```

> **Примечание:** `lead_temperature` и `collected_data` в ответе `/restore` вычисляются
> API-обёрткой из snapshot (аналогично `/process`). Endpoint `/restore` — полностью
> на стороне обёртки, его схему определяет разработчик интеграции.

---

#### `GET /api/v1/flows` — список доступных flow

**Response:**

```json
{
  "flows": [
    {"name": "spin_selling", "description": "SPIN Selling methodology", "phases": ["situation", "problem", "implication", "need_payoff", "presentation", "close"]},
    {"name": "bant", "description": "Budget, Authority, Need, Timeline", "phases": ["budget", "authority", "need", "timeline"]},
    ...
  ]
}
```

---

#### `GET /api/v1/configs` — список доступных конфигураций

Возвращает список named-конфигов, загруженных из YAML-файлов AI‑сервиса.

**Response:**

```json
{
  "configs": [
    {"name": "default", "description": "Default configuration"},
    {"name": "tenant_alpha", "description": "Tenant Alpha custom config"},
    ...
  ]
}
```

---

#### `GET /api/v1/health` — проверка здоровья

**Response:**

```json
{
  "status": "ok",
  "llm_available": true,
  "embeddings_loaded": true,
  "reranker_loaded": true,
  "version": "1.0.0"
}
```

---

#### `POST /api/v1/configs/{name}/override` — runtime config override (hot-reload)

Применить точечные override параметров constants без редеплоя. Принимаются только безопасные ключи из `SAFE_OVERRIDE_KEYS`.

**Request body:**

```json
{
  "overrides": {
    "guard": {"max_turns": 30, "high_frustration_threshold": 8},
    "limits": {"max_gobacks": 5},
    "disambiguation": {"high_confidence": 0.90}
  }
}
```

**Response:**

```json
{
  "applied": ["guard", "limits", "disambiguation"],
  "rejected": {}
}
```

Если ключ не входит в `SAFE_OVERRIDE_KEYS`, он попадёт в `rejected`:

```json
{
  "applied": ["guard"],
  "rejected": {"intents": "structural key, requires redeploy"}
}
```

**Safe override keys:**

| Ключ | Описание |
|---|---|
| `limits` | max_gobacks, max_consecutive_objections и т.д. |
| `lead_scoring` | skip_phases, signals, temperature thresholds |
| `guard` | high_frustration_threshold, max_turns и т.д. |
| `frustration` | frustration thresholds |
| `fallback` | rephrase_templates, options_templates |
| `cta` | CTA generation parameters |
| `circular_flow` | allowed_gobacks |
| `response_directives` | response generation guidance |
| `disambiguation` | confidence thresholds, gap_threshold |

> **Caveat (SessionManager):** Если сервер использует `SessionManager` с кэшированием ботов, override влияет только на **новые сессии**. Кэшированные сессии продолжат работать со старыми настройками до пересоздания (close + re-open). В stateless-режиме (рекомендуемом) override вступает в силу со следующего запроса.

---

#### `GET /api/v1/configs/{name}/override` — получить текущие overrides

**Response:**

```json
{
  "config_name": "default",
  "overrides": {
    "guard": {"max_turns": 30}
  }
}
```

Если overrides не заданы, возвращается пустой объект `"overrides": {}`.

---

#### `DELETE /api/v1/configs/{name}/override` — очистить overrides

**Response:**

```json
{
  "config_name": "default",
  "cleared": true
}
```

`cleared: false` означает, что overrides для этого config_name и так отсутствовали.

---

### 3.2 Входные данные (что бот ожидает)

На каждый ход бот получает **одну текстовую строку** — сообщение пользователя.
Всё состояние передаётся в аргументах запроса:

| Поле | Тип | Описание |
|---|---|---|
| `client_id` | `str` | Идентификатор клиента/тенанта |
| `session_id` | `str` | Идентификатор диалога |
| `flow_name` | `str` | Имя sales flow |
| `config_name` | `str` | Имя конфигурации (YAML на AI‑сервисе) |
| `user_message` | `str` | Текст сообщения |
| `snapshot` | `dict \| null` | Предыдущее состояние (null для нового диалога) |
| `history_tail` | `list` | Последние 4 хода `[{"user": "...", "bot": "..."}]` |

Медиа-вложения (voice/image/file) ядром напрямую не обрабатываются — они должны быть
преобразованы в текст до вызова API.

### 3.3 Выходные данные (Structured JSON)

Ответ `process()` — **строгий JSON** с фиксированной схемой (18 полей, см. таблицу в 3.1).

Минимальное подмножество для отправки клиенту:
- `response` — текст ответа
- `is_final` — завершён ли диалог

Для сохранения и аналитики (добавляются API-обёрткой):
- `snapshot` — получить через `bot.to_snapshot()` **после** `process()`, сохранить в MongoDB
- `decision_trace` — сохранить для аналитиков (требует `enable_tracing=True` в конструкторе `SalesBot`)

Остальные поля (`intent`, `lead_score`, `tone`, `spin_phase`, ...) — для мониторинга и дашбордов.

---

## 4. Схемы данных для MongoDB

### 4.1 Структура Snapshot

Snapshot — полный слепок состояния бота. Передаётся в запросе, возвращается в ответе.
Хранится внешней системой в MongoDB (коллекция `snapshots` или поле внутри документа диалога).

```json
{
  "version": "1.0",
  "conversation_id": "abc123",
  "client_id": "tenant-42",
  "timestamp": 1706000000.123,

  "flow_name": "spin_selling",
  "config_name": "tenant_alpha",

  "state_machine": {
    "state": "spin_problem",
    "current_phase": "problem",

    "collected_data": {
      "company_size": "50-100",
      "current_tools": "Excel",
      "business_type": "retail",
      "pain_point": null,
      "pain_impact": null,
      "desired_outcome": null,
      "value_acknowledged": false,
      "decision_maker": null,
      "decision_timeline": null,
      "budget_range": null,
      "contact_info": null,
      "persona": null,
      "competitor_mentioned": false,
      "competitor_name": null,
      "implication_probed": false,
      "need_payoff_probed": false
    },

    "in_disambiguation": false,
    "disambiguation_context": null,
    "pre_disambiguation_state": null,
    "turns_since_last_disambiguation": 5,

    "intent_tracker": {
      "last_intent": "explicit_problem",
      "prev_intent": "company_info",
      "last_state": "spin_problem",
      "current_streak": {"intent": "explicit_problem", "count": 1},
      "turn_number": 5,
      "history_length": 5,
      "intent_totals": {"explicit_problem": 1, "company_info": 1, "greeting": 1},
      "category_totals": {"objection": 1, "question": 0},
      "category_streaks": {"objection": 0, "question": 0},
      "recent_intents": ["greeting", "company_info", "explicit_problem"]
    },

    "circular_flow": {
      "goback_count": 0,
      "remaining": 2,
      "history": []
    },

    "last_action": "ask_current_tools",
    "_state_before_objection": null
  },

  "guard": {
    "turn_count": 5,
    "state_history": ["greeting", "spin_situation", "spin_problem"],
    "message_history": ["привет", "у нас магазин, 50 сотрудников"],
    "phase_attempts": {"greeting": 1, "spin_situation": 2, "spin_problem": 2},
    "start_time": 1706000000.0,
    "elapsed_seconds": 45.2,
    "last_progress_turn": 4,
    "collected_data_count": 2,
    "frustration_level": 2,
    "intent_history": ["greeting", "company_info", "explicit_problem"],
    "last_intent": "explicit_problem",
    "pre_intervention_triggered": false,
    "consecutive_tier_2_count": 0,
    "consecutive_tier_2_state": null
  },

  "lead_scorer": {
    "current_score": 35,
    "raw_score": 35.0,
    "signals_history": ["explicit_problem"],
    "_signals_history_full": [{"signal": "explicit_problem", "points": 15}],
    "turn_count": 5,
    "decay_applied_this_turn": false
  },

  "fallback": {
    "total_count": 0,
    "tier_counts": {},
    "state_counts": {},
    "last_tier": null,
    "last_state": null,
    "dynamic_cta_counts": {},
    "consecutive_tier_2_count": 0,
    "consecutive_tier_2_state": null,
    "_used_templates": {}
  },

  "objection_handler": {"objection_attempts": {"PRICE": 1}},

  "context_window": [
    {
      "user_message": "Привет",
      "bot_response": "Добрый день! Расскажите о вашей компании.",
      "intent": "greeting",
      "confidence": 0.98,
      "action": "ask_company_info",
      "state": "greeting",
      "next_state": "spin_situation",
      "extracted_data": {}
    }
  ],

  "_context_window_full": {
    "turns": ["..."],
    "episodic_memory": {"episodes": [], "max_episodes": 50}
  },

  "history": [],
  "history_compact": {
    "summary": ["..."],
    "key_facts": ["..."],
    "objections": ["..."],
    "decisions": ["..."],
    "open_questions": ["..."],
    "next_steps": ["..."]
  },
  "history_compact_meta": {
    "compacted_turns": 12,
    "tail_size": 4,
    "compacted_at": 1706000000.123,
    "compaction_version": "1.0",
    "llm_model": "qwen3:14b"
  },

  "last_action": "ask_current_tools",
  "last_intent": "explicit_problem",
  "last_bot_message": "Какую систему используете сейчас?",

  "metrics": {
    "conversation_id": "conv_abc123",
    "turns": 5,
    "phase_turns": {"spin_situation": 2, "spin_problem": 3},
    "intents_sequence": ["greeting", "company_info", "explicit_problem"],
    "objections": [],
    "fallback_count": 0,
    "fallback_by_tier": {},
    "tone_history": ["neutral", "neutral", "interested"],
    "lead_score_history": [0, 10, 25],
    "turn_records": [
      {
        "turn_number": 1,
        "state": "greeting",
        "intent": "greeting",
        "timestamp": 1700000000.0,
        "tone": "neutral",
        "response_time_ms": 120,
        "fallback_used": false,
        "fallback_tier": null
      }
    ],
    "collected_data": {"company_name": "Рога и Копыта", "current_tools": "Excel"},
    "outcome": null,
    "start_time": 1700000000.0,
    "end_time": null
  }
}
```

#### Описание ключевых блоков Snapshot

| Блок | Описание |
|---|---|
| `version` | Версия схемы snapshot (`"1.0"`) |
| `conversation_id` | Уникальный ID диалога |
| `client_id` | ID тенанта. Обязателен для защиты от восстановления чужого snapshot |
| `timestamp` | Unix timestamp создания snapshot |
| `flow_name` | Активная методология продаж |
| `state_machine` | Ядро состояния: текущий state, phase, собранные данные, трекер интентов, история goback |
| `state_machine.collected_data` | Все извлечённые из диалога данные клиента. 16+ стандартных полей + динамические |
| `state_machine.intent_tracker` | Статистика по интентам: последний, предыдущий, streak, суммы по категориям |
| `state_machine.circular_flow` | Контроль «возвратов назад» (goback) — сколько раз клиент просил вернуться |
| `guard` | Состояние защитного механизма: уровень фрустрации, история состояний и интентов, счётчики tier-ов |
| `lead_scorer` | Текущий lead score, история сигналов, raw score |
| `fallback` | Счётчики использования fallback-ов по tier-ам |
| `objection_handler` | Счётчики попыток обработки возражений по типам |
| `context_window` | Последние turn-ы для паттернового анализа |
| `_context_window_full` | Расширенный контекст + эпизодическая память (для точного восстановления) |
| `history` | Всегда пустой массив — последние сообщения берутся из `history_tail` |
| `history_compact` | Сжатое резюме диалога (если была компакция) |
| `history_compact_meta` | Метаданные компакции: сколько turn-ов сжато, когда, какой LLM |
| `last_action` / `last_intent` / `last_bot_message` | Последние значения для контекста |
| `metrics` | Агрегированные метрики диалога |

#### Поля `collected_data` (стандартные)

| Поле | Тип | Описание |
|---|---|---|
| `company_size` | `string \| null` | Размер компании (small/medium/large или число) |
| `current_tools` | `string \| null` | Текущая CRM/POS система |
| `business_type` | `string \| null` | Тип бизнеса |
| `pain_point` | `string \| null` | Основная боль/проблема |
| `pain_impact` | `string \| null` | Финансовое/операционное влияние проблемы |
| `desired_outcome` | `string \| null` | Желаемый результат |
| `value_acknowledged` | `boolean` | Клиент подтвердил ценность |
| `decision_maker` | `string \| null` | Кто принимает решение |
| `decision_timeline` | `string \| null` | Когда будет решение |
| `budget_range` | `string \| null` | Бюджет |
| `contact_info` | `object \| null` | `{phone, email, name, valid}` |
| `persona` | `string \| null` | Тип персоны (если задана) |
| `competitor_mentioned` | `boolean` | Был ли упомянут конкурент |
| `competitor_name` | `string \| null` | Имя конкурента |
| `implication_probed` | `boolean` | Фаза implication пройдена |
| `need_payoff_probed` | `boolean` | Фаза need-payoff пройдена |

> **Примечание:** `collected_data` может содержать дополнительные динамические поля,
> извлечённые классификатором. MongoDB-документ не требует жёсткой схемы.

---

### 4.2 Структура Config (справочно)

Config — конфигурация поведения бота. Хранится в YAML‑файлах на стороне AI‑сервиса.
Внешняя система указывает `config_name` в запросе, сервис загружает соответствующий YAML.

Этот раздел — **справочная документация** по структуре конфига, чтобы аналитики
понимали, какие параметры можно настраивать через админ-панель (раздел 7).

Config состоит из двух частей:
1. **Constants** — глобальные константы (лимиты, интенты, пороги, lead scoring)
2. **Flow Config** — конфигурация конкретного flow (состояния, переходы, шаблоны)

#### 4.2.1 Constants (основные секции)

```json
{
  "limits": {
    "max_consecutive_objections": 3,
    "max_total_objections": 5,
    "max_gobacks": 2,
    "phase_origin_objection_escape": 2,
    "persona_objection_limits": {
      "aggressive": {"consecutive": 2, "total": 4},
      "passive": {"consecutive": 4, "total": 6}
    }
  },

  "intents": {
    "go_back": ["go_back", "correct_info"],
    "categories": {
      "objection": ["objection_price", "objection_competitor", "objection_no_time", "..."],
      "exit": ["rejection", "farewell"],
      "escalation": ["request_human", "need_help", "speak_to_manager"],
      "frustration": ["frustration", "impatience"],
      "sensitive": ["legal_question", "compliance", "gdpr_question", "refund_request"],
      "positive": ["demo_request", "contact_provided", "callback_request", "..."],
      "question": ["price_question", "feature_question", "integration_question", "..."],
      "price_related": ["price_question", "pricing_details", "discount_question", "..."]
    },
    "intent_action_overrides": {
      "price_question": "answer_with_pricing",
      "demo_request": "schedule_demo",
      "contact_provided": "collect_contact"
    },
    "intent_taxonomy": {
      "demo_request": {
        "category": "positive",
        "super_category": "user_action",
        "semantic_domain": "purchase",
        "fallback_action": "schedule_demo",
        "fallback_transition": "close",
        "priority": "critical",
        "bypass_disambiguation": true
      }
    }
  },

  "disambiguation": {
    "thresholds": {
      "high_confidence": 0.85,
      "medium_confidence": 0.65,
      "low_confidence": 0.45,
      "min_confidence": 0.30
    },
    "gap_threshold": 0.20,
    "options": {"max_options": 3, "min_option_confidence": 0.25},
    "cooldown_turns": 3
  },

  "lead_scoring": {
    "signals": {
      "contact_provided": {"points": 35},
      "demo_request": {"points": 30},
      "price_with_size": {"points": 25},
      "explicit_problem": {"points": 15},
      "objection_no_need": {"points": -25},
      "frustration": {"points": -15}
    },
    "skip_phases": {
      "cold": [],
      "warm": ["spin_implication", "spin_need_payoff"],
      "hot": ["spin_problem", "spin_implication", "spin_need_payoff"],
      "very_hot": ["spin_situation", "spin_problem", "spin_implication", "spin_need_payoff"]
    }
  },

  "guard": {
    "high_frustration_threshold": 7,
    "tier_2_escalation_threshold": 3
  },

  "cta": {
    "enabled": true,
    "min_confidence": 0.7,
    "max_per_conversation": 3,
    "skip_actions": ["escalate_to_human", "soft_close"],
    "skip_states": ["greeting", "escalated"]
  },

  "circular_flow": {
    "allowed_gobacks": {
      "spin_problem": "spin_situation",
      "spin_implication": "spin_problem"
    }
  }
}
```

#### 4.2.2 Flow Config (основные секции)

```json
{
  "name": "spin_selling",
  "version": "1.0",
  "description": "SPIN Selling methodology",

  "states": {
    "greeting": {
      "phase": null,
      "is_final": false,
      "required_data": [],
      "goal": "Поприветствовать клиента",
      "transitions": {
        "greeting": "spin_situation",
        "company_info": "spin_situation",
        "default": "spin_situation"
      },
      "rules": {
        "greeting": "greet_and_ask",
        "default": "greet_and_ask"
      }
    },
    "spin_situation": {
      "phase": "situation",
      "is_final": false,
      "required_data": ["company_size", "current_tools"],
      "goal": "Выяснить ситуацию клиента",
      "transitions": {
        "company_info": "spin_situation",
        "explicit_problem": "spin_problem",
        "default": "spin_situation"
      },
      "rules": {
        "company_info": "probe_situation",
        "price_question": "answer_with_pricing",
        "default": "probe_situation"
      },
      "max_turns_in_state": 5
    },
    "...": "..."
  },

  "phases": {
    "order": ["situation", "problem", "implication", "need_payoff", "presentation", "close"],
    "mapping": {
      "situation": "spin_situation",
      "problem": "spin_problem",
      "implication": "spin_implication",
      "need_payoff": "spin_need_payoff",
      "presentation": "presentation",
      "close": "close"
    }
  },

  "entry_points": {
    "default": "greeting",
    "escalation": "escalated"
  },

  "templates": {
    "probe_situation": {
      "template": "Задай вопрос о текущей ситуации клиента...",
      "parameters": ["collected_data", "history"]
    },
    "answer_with_pricing": {
      "template": "Ответь на вопрос о цене, используя базу знаний...",
      "parameters": ["knowledge_results", "collected_data"]
    }
  }
}
```

#### 4.2.3 Feature Flags (передаются в config)

```json
{
  "features": {
    "structured_logging": true,
    "metrics_tracking": true,
    "multi_tier_fallback": true,
    "conversation_guard": true,
    "tone_analysis": true,
    "response_variations": true,
    "question_deduplication": true,
    "lead_scoring": true,
    "objection_handler": true,
    "cta_generator": true,
    "intent_disambiguation": true,
    "cascade_classifier": true,
    "llm_classifier": true,
    "cascade_tone_analyzer": true,
    "context_policy_overlays": true,
    "context_response_directives": true
  }
}
```

---

### 4.3 MongoDB: рекомендуемые коллекции

#### Коллекция `conversations` — диалоги

```json
{
  "_id": "ObjectId",
  "session_id": "chat-123",
  "client_id": "tenant-42",
  "user_external_id": "whatsapp:79001234567",
  "status": "bot_active",
  "flow_name": "spin_selling",
  "current_state": "spin_problem",
  "current_phase": "problem",
  "lead_score": 35,
  "lead_temperature": "warm",
  "outcome": null,
  "total_turns": 5,
  "snapshot": { "..." : "полный snapshot (раздел 4.1)" },
  "config_name": "tenant_alpha",
  "collected_data": {"company_size": "50", "current_tools": "Excel"},
  "created_at": "ISODate",
  "updated_at": "ISODate",
  "completed_at": null
}
```

Статусы: `bot_active`, `operator_active`, `escalated`, `completed`, `paused`

Outcome: `success`, `demo_scheduled`, `soft_close`, `rejected`, `abandoned`, `timeout`, `error`

#### Коллекция `messages` — сообщения

```json
{
  "_id": "ObjectId",
  "conversation_id": "ObjectId ref",
  "turn_number": 3,
  "role": "user",
  "content": "А сколько стоит?",
  "intent": "price_question",
  "confidence": 0.92,
  "action": "answer_with_pricing",
  "state_before": "spin_situation",
  "state_after": "spin_situation",
  "tone": "neutral",
  "frustration_level": 1,
  "lead_score_after": 20,
  "fallback_used": false,
  "objection_detected": false,
  "cta_added": false,
  "decision_trace": { "..." : "полный trace (раздел 5)" },
  "response_time_ms": 1250.5,
  "created_at": "ISODate"
}
```

#### Коллекция `tenant_settings` — настройки тенантов

Маппинг тенант → config_name (какой YAML-конфиг AI‑сервиса использовать).

```json
{
  "_id": "ObjectId",
  "client_id": "tenant-42",
  "config_name": "tenant_alpha",
  "flow_name": "spin_selling",
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

#### Коллекция `operator_handoffs` — передачи бот ↔ оператор

```json
{
  "_id": "ObjectId",
  "conversation_id": "ObjectId ref",
  "direction": "bot_to_operator",
  "reason": "frustration_threshold",
  "operator_id": "op-789",
  "turn_number": 8,
  "snapshot_at_handoff": { "..." : "snapshot на момент передачи" },
  "created_at": "ISODate"
}
```

#### Индексы

```javascript
// conversations
db.conversations.createIndex({ "client_id": 1, "session_id": 1 }, { unique: true })
db.conversations.createIndex({ "client_id": 1, "status": 1 })
db.conversations.createIndex({ "updated_at": 1 })

// messages
db.messages.createIndex({ "conversation_id": 1, "turn_number": 1 })
db.messages.createIndex({ "conversation_id": 1, "created_at": 1 })

// tenant_settings
db.tenant_settings.createIndex({ "client_id": 1 }, { unique: true })

// operator_handoffs
db.operator_handoffs.createIndex({ "conversation_id": 1, "created_at": -1 })
```

---

## 5. Decision Trace (обязательный)

**Decision trace возвращается в каждом ответе** при условии, что `SalesBot` создан
с `enable_tracing=True`. Это основной инструмент прозрачности для аналитиков.
Сохраняется в коллекции `messages` рядом с сообщением.

> **Важно:** По умолчанию `enable_tracing=False` в конструкторе `SalesBot` (`src/bot.py:106`),
> и `decision_trace` будет `None`. API-обёртка **обязана** передавать `enable_tracing=True`
> при создании экземпляра `SalesBot`.

### 5.1 Структура decision trace

```json
{
  "metadata": {
    "turn_number": 3,
    "timestamp": 1706000000.123,
    "elapsed_ms": 1250.5,
    "user_message": "А сколько стоит?"
  },

  "classification": {
    "top_intent": "price_question",
    "confidence": 0.92,
    "all_scores": {"price_question": 0.92, "general_interest": 0.05},
    "method_used": "llm",
    "disambiguation_triggered": false,
    "extracted_data": {"company_size": "50"},
    "classification_time_ms": 340.2
  },

  "tone_analysis": {
    "detected_tone": "neutral",
    "frustration_level": 1,
    "markers_found": [],
    "should_apologize": false,
    "should_offer_exit": false,
    "analysis_time_ms": 12.5
  },

  "guard_check": {
    "intervention_triggered": false,
    "can_continue": true,
    "frustration_at_check": 1,
    "check_time_ms": 0.8
  },

  "state_machine": {
    "prev_state": "spin_situation",
    "next_state": "spin_situation",
    "prev_phase": "situation",
    "next_phase": "situation",
    "action": "answer_with_pricing",
    "is_final": false,
    "processing_time_ms": 2.1,
    "required_data_status": {
      "required": ["company_size", "current_tools"],
      "collected": ["company_size"],
      "missing": ["current_tools"],
      "completion_percent": 50.0
    }
  },

  "lead_score": {
    "previous_score": 15,
    "new_score": 20,
    "score_change": 5,
    "signals_applied": ["price_question"],
    "temperature": "cold"
  },

  "fallback": {
    "tier": null,
    "reason": null,
    "alternatives_considered": [],
    "fallback_action": null,
    "fallback_message": null,
    "recovery_possible": true
  },

  "objection": {
    "detected": false,
    "detected_type": null,
    "attempt_number": 0,
    "strategy_selected": null,
    "should_soft_close": false,
    "consecutive_count": 0,
    "total_count": 0
  },

  "policy_override": {
    "was_overridden": true,
    "original_action": "ask_problem",
    "override_action": "answer_with_pricing",
    "reason_codes": ["policy.price_override"],
    "decision": "PRICE_QUESTION"
  },

  "response": {
    "template_key": null,
    "cta_added": false,
    "response_length": 156,
    "generation_time_ms": 890.3
  },

  "llm_traces": [
    {
      "request_id": "req_abc123",
      "purpose": "classification",
      "tokens_input": 1200,
      "tokens_output": 50,
      "latency_ms": 340.2,
      "success": true
    },
    {
      "request_id": "req_def456",
      "purpose": "response_generation",
      "tokens_input": 2800,
      "tokens_output": 180,
      "latency_ms": 890.3,
      "success": true
    }
  ],

  "context_window": {
    "sliding_window": [],
    "episodic_events": [],
    "momentum_breakdown": {},
    "engagement_breakdown": {},
    "client_profile_snapshot": {}
  },

  "personalization": {
    "template_selected": "",
    "selection_reason": "",
    "substitutions": {},
    "business_context": "",
    "industry_context": ""
  },

  "client_agent": null,

  "timing": {
    "tone_analysis_ms": 12.5,
    "guard_check_ms": 0.8,
    "classification_ms": 340.2,
    "state_machine_ms": 2.1,
    "response_generation_ms": 890.3,
    "total_turn_ms": 1250.5,
    "bottleneck": "response_generation"
  },

  "bot_response": "Стоимость зависит от тарифа. Для компании в 50 сотрудников..."
}
```

### 5.2 Что видят аналитики в decision trace

| Блок | Что показывает |
|---|---|
| `classification` | Как бот понял клиента: какой intent, с какой уверенностью, каким методом |
| `tone_analysis` | Настроение клиента: тон, фрустрация, нужно ли извиниться |
| `guard_check` | Сработала ли защита от зацикливания |
| `fallback` | Информация о fallback: tier, причина, выбранное действие, возможность восстановления |
| `state_machine` | Логика перехода: из какого состояния в какое, какое действие выбрано, сколько данных собрано |
| `lead_score` | Динамика скоринга: сколько было → сколько стало, какие сигналы повлияли |
| `objection` | Возражения: тип (`detected_type`), номер попытки, стратегия, общее количество |
| `policy_override` | Были ли переопределения: какое действие было → какое стало, почему |
| `response` | Параметры генерации ответа |
| `llm_traces` | Все вызовы LLM: purpose, токены, латентность |
| `context_window` | Состояние контекстного окна: sliding window, episodic events, momentum, engagement |
| `personalization` | Персонализация ответа: шаблон, бизнес-контекст, индустрия |
| `client_agent` | Трассировка клиентского агента (только для симулятора, `null` в продакшене) |
| `timing` | Тайминги всех этапов обработки, bottleneck |

---

## 6. Протокол передачи диалога (бот ↔ оператор)

### 6.1 Состояния диалога

```
                  ┌──────────────┐
                  │  BOT_ACTIVE  │ ← Бот ведёт диалог
                  └──────┬───────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
          ▼              ▼              ▼
    ┌───────────┐  ┌───────────┐  ┌───────────┐
    │ ESCALATED │  │ INTERCEPT │  │ COMPLETED │
    │(бот решил)│  │(оператор) │  │ (финал)   │
    └─────┬─────┘  └─────┬─────┘  └───────────┘
          │              │
          ▼              ▼
    ┌─────────────────────┐
    │  OPERATOR_ACTIVE    │ ← Оператор ведёт диалог
    └──────────┬──────────┘
               │
          ┌────┼────┐
          │         │
          ▼         ▼
    ┌───────────┐  ┌───────────┐
    │ BOT_ACTIVE│  │ COMPLETED │
    │(возврат)  │  │ (финал)   │
    └───────────┘  └───────────┘
```

### 6.2 Триггеры эскалации (бот → оператор)

Бот инициирует передачу оператору при:

| Триггер | Описание |
|---|---|
| Явный запрос человека | Интенты из категории `escalation` (request_human, speak_to_manager, ...) |
| Sensitive topics | Интенты из категории `sensitive` (legal/compliance/complaints) |
| Фрустрация | Повторные интенты категории `frustration` (порог `frustration_threshold`, default=3) |
| Повторные непонимания | `unclear` >= `misunderstanding_threshold` (default=4) |
| High‑value + complex | `company_size >= 100` и intent ∈ {`custom_integration`, `enterprise_features`, `sla_question`} |

В ответе бота эскалация проявляется как `action = "escalate_to_human"` и `is_final = true`.

### 6.3 Три сценария операторского управления

| # | Сценарий | UI-элемент | Описание |
|---|----------|------------|----------|
| 1 | **Бот ведёт от начала до конца** | Нет (default) | `status = bot_active`. Все входящие сообщения роутятся в AI‑сервис. |
| 2 | **Оператор перехватывает диалог** | Кнопка «Перехватить» | Оператор забирает активный диалог. Snapshot сохраняется, сообщения идут оператору. |
| 3 | **Оператор возвращает диалог боту** | Кнопка «Продолжить» | Оператор передаёт обратно. Бот восстанавливается из snapshot. |

### 6.4 Реализация сценариев (ответственность внешней системы)

**Сценарий 1: бот ведёт**

```
Входящее сообщение
  → Проверить status в MongoDB
  → Если bot_active: POST /api/v1/process { snapshot, config, message, ... }
  → Получить ответ
  → Сохранить snapshot, message, trace в MongoDB
  → Отправить response клиенту
  → Если is_final: status = completed
```

**Сценарий 2: перехват**

```
Оператор нажимает «Перехватить»
  → Загрузить текущий snapshot из MongoDB
  → Сохранить operator_handoff с snapshot
  → status = operator_active
  → Все последующие сообщения идут оператору
```

**Сценарий 3: возврат боту**

```
Оператор нажимает «Продолжить»
  → Загрузить snapshot из operator_handoff
  → Загрузить хвост истории (включая сообщения оператора)
  → Замаппить operator → bot в history_tail
  → status = bot_active
  → Следующее сообщение пойдёт в POST /api/v1/process с восстановленным snapshot
```

**Маппинг history_tail при возврате от оператора:**

Бот ожидает `history_tail` в формате `[{"user": "...", "bot": "..."}]`.
Сообщения оператора маппятся как `bot`:

```python
def normalize_history_tail(raw_messages: list[dict]) -> list[dict]:
    """
    БД: [{"role": "user"|"bot"|"operator", "content": "..."}]
    Ядро: [{"user": "...", "bot": "..."}]
    """
    result = []
    i = 0
    while i < len(raw_messages):
        msg = raw_messages[i]
        if msg["role"] == "user":
            user_text = msg["content"]
            bot_text = ""
            if i + 1 < len(raw_messages) and raw_messages[i + 1]["role"] in ("bot", "operator"):
                bot_text = raw_messages[i + 1]["content"]
                i += 1
            result.append({"user": user_text, "bot": bot_text})
        i += 1
    return result
```

**Условия доступности кнопок:**

| Кнопка | Видна когда | Скрыта когда |
|--------|------------|-------------|
| «Перехватить» | `status = bot_active` | `status ∈ {operator_active, completed}` |
| «Продолжить» | `status = operator_active` и есть snapshot | `status ∈ {bot_active, completed}` |

### 6.5 Известные ограничения

| # | Ограничение | Рекомендация |
|---|-------------|-------------|
| 1 | Snapshot фиксирует состояние на момент перехвата. Новые данные, собранные оператором, бот не увидит | Обогатить `snapshot.state_machine.collected_data` перед возвратом, либо оператор передаёт заметку |
| 2 | Бот не знает длительность паузы оператора | Скорректировать `guard` в snapshot перед восстановлением |

---

## 7. Scope админ-панели

Админ-панель управляет **конфигурациями** бота, которые хранятся в YAML‑файлах
на стороне AI‑сервиса.

### 7.1 Tier 1: Базовая конфигурация (для менеджеров/продажников)

#### 7.1.1 Выбор sales flow

Переключение активной методологии продаж:

| Flow | Описание |
|---|---|
| `spin_selling` | SPIN Selling (по умолчанию) |
| `bant` | Budget, Authority, Need, Timeline |
| `meddic` | Metrics, Economic Buyer, Decision Criteria, Decision Process, Identify Pain, Champion |
| `aida` | Attention, Interest, Desire, Action |
| `neat` | Need, Economic impact, Access to authority, Timeline |
| `snap` | Simple, iNvaluable, Aligned, Priority |
| `fab` | Features, Advantages, Benefits |
| `relationship` | Relationship selling |
| `inbound` | Inbound methodology |
| `autonomous` | Автономный LLM-driven flow |
| `challenger` | Challenger selling |
| `command` | Command/Directive selling |
| `consultative` | Consultative selling |
| `customer_centric` | Customer‑centric selling |
| `demo_first` | Demo‑first flow |
| `gap` | Gap selling |
| `sandler` | Sandler selling |
| `social` | Social selling |
| `solution` | Solution selling |
| `transactional` | Transactional selling |
| `value` | Value selling |

#### 7.1.2 Feature Flags (60+ тогглов)

| Группа | Примеры флагов | Назначение |
|---|---|---|
| Phase 0 | `structured_logging`, `metrics_tracking` | Инфраструктура |
| Phase 1 | `multi_tier_fallback`, `conversation_guard` | Безопасность и надёжность |
| Phase 2 | `tone_analysis`, `response_variations`, `question_deduplication` | Естественность |
| Phase 3 | `lead_scoring`, `objection_handler`, `cta_generator` | Оптимизация продаж |
| Phase 4 | `intent_disambiguation`, `cascade_classifier` | Классификация |
| Phase 5 | `secondary_intent_detection`, `structural_frustration_detection` | Продвинутые функции |
| LLM | `llm_classifier`, `confidence_router` | Режим классификатора |
| Tone | `cascade_tone_analyzer`, `tone_semantic_tier2`, `tone_llm_tier3` | Анализ тона |
| Context | `context_policy_overlays`, `context_response_directives` | Контекстные политики |

Есть пресеты для группового включения: `safe`, `risky`, `phase_1`..`phase_5`.

#### 7.1.3 База знаний (Knowledge Base)

17 категорий, 1 969 секций. Каждая секция:

```yaml
sections:
  - topic: "Тарифы для малого бизнеса"
    priority: 8
    keywords: ["тариф", "малый бизнес", "цена"]
    facts: |
      Тариф «Старт» — 990 руб/мес за 1 кассу.
      Включает: товароучёт, аналитику, 1 пользователя.
      Подключение бесплатно.
```

| Категория | Секций | Описание |
|---|---|---|
| `pricing` | 286 | Цены, тарифы, условия оплаты |
| `products` | 273 | Продукты и возможности |
| `equipment` | 316 | Оборудование, модели, спецификации |
| `support` | 201 | Поддержка, SLA, контакты |
| `tis` | 191 | Терминалы, кассы |
| `features` | 90 | Функциональность |
| `integrations` | 86 | Интеграции |
| `regions` | 130 | Регионы и филиалы |
| `inventory` | 93 | Складской учёт |
| `analytics` | 63 | Аналитика и отчёты |
| `fiscal` | 68 | Фискальные требования |
| `employees` | 55 | Управление сотрудниками |
| `mobile` | 35 | Мобильное приложение |
| `stability` | 45 | Надёжность и uptime |
| `competitors` | 7 | Конкурентное позиционирование |
| `promotions` | 26 | Акции и промо |
| `faq` | 4 | Частые вопросы |

> **Примечание:** база знаний загружается при старте AI‑сервиса и живёт в памяти.
> Она **не передаётся** в каждом API‑запросе. Обновление KB — отдельная задача
> (перезагрузка сервиса или hot-reload эндпоинт).

#### 7.1.4 Управление возражениями

8 типов возражений с настраиваемыми параметрами:

| Тип возражения | Паттернов | Стратегия | Настраиваемое |
|---|---|---|---|
| `PRICE` | 17 | 4P's (рациональная) | Шаблоны ответов, follow-up вопросы |
| `COMPETITOR` | 18 | 4P's | Шаблоны, сравнения |
| `NO_TIME` | 13 | 3F's (эмоциональная) | Шаблоны, предложения |
| `THINK` | 9 | 3F's | Шаблоны |
| `NO_NEED` | 11 | 4P's | Шаблоны |
| `TRUST` | 11 | 3F's | Кейсы, отзывы |
| `TIMING` | 9 | 3F's | Шаблоны |
| `COMPLEXITY` | 8 | 4P's | Шаблоны |

### 7.2 Tier 2: Продвинутая настройка (для тимлидов/продуктологов)

> Параметры Tier 2 можно менять без редеплоя через `POST /api/v1/configs/{name}/override`
> (см. раздел 3.1). Ключи: `guard`, `limits`, `lead_scoring`, `cta`, `fallback`,
> `frustration`, `disambiguation`, `response_directives`, `circular_flow`.

#### 7.2.1 Лимиты диалога

| Параметр | По умолчанию | Описание |
|---|---|---|
| `max_turns` | 25 | Максимум ходов в диалоге |
| `max_phase_attempts` | 3 | Максимум попыток в одной фазе |
| `max_same_state` | 4 | Максимум ходов в одном состоянии |
| `max_gobacks` | 2 | Максимум возвратов назад |
| `timeout_seconds` | 1800 | Таймаут диалога (30 мин) |
| `high_frustration_threshold` | 7 | Порог фрустрации для эскалации |

#### 7.2.2 Диалоговые политики (policy overlays)

| Политика | Триггер | Действие |
|---|---|---|
| `repair_mode` | Диалог застрял / зацикливание | Уточнить / предложить варианты |
| `objection_overlay` | Повторные возражения | Усилить аргументацию / эскалировать |
| `price_question_overlay` | Вопрос о цене | Гарантированно ответить с ценой |
| `breakthrough_overlay` | Позитивный сдвиг | Мягкий CTA |
| `conservative_overlay` | Низкая уверенность | Осторожный режим |

#### 7.2.3 Настройки LLM и поиска

| Параметр | Описание |
|---|---|
| `llm.model` | Модель LLM (qwen3:14b) |
| `llm.base_url` | URL Ollama API |
| `llm.timeout` | Таймаут запросов (120 сек) |
| `retriever.use_embeddings` | Включить семантический поиск |
| `retriever.thresholds.exact` | Порог точного совпадения (1.0) |
| `retriever.thresholds.lemma` | Порог леммного поиска (0.15) |
| `retriever.thresholds.semantic` | Порог семантического поиска (0.5) |
| `reranker.enabled` | Включить reranker |
| `reranker.threshold` | Порог reranker-а |

### 7.3 Tier 3: Экспертная конфигурация (для разработчиков)

#### 7.3.1 Таксономия интентов

247 интентов, каждый с атрибутами:

```yaml
demo_request:
  category: positive
  super_category: user_action
  semantic_domain: purchase
  fallback_action: schedule_demo
  fallback_transition: close
  priority: critical
  bypass_disambiguation: true
```

#### 7.3.2 Lead scoring сигналы

| Сигнал | Вес | Описание |
|---|---|---|
| `contact_provided` | +35 | Клиент дал контакт |
| `demo_request` | +30 | Запрос демо |
| `price_with_size` | +25 | Цена + размер компании |
| `callback_request` | +25 | Запрос обратного звонка |
| `consultation_request` | +20 | Запрос консультации |
| `explicit_problem` | +15 | Озвучил проблему |
| `competitor_comparison` | +12 | Сравнение с конкурентом |
| `budget_mentioned` | +10 | Упоминание бюджета |
| `timeline_mentioned` | +10 | Упоминание сроков |
| `multiple_questions` | +8 | Несколько вопросов подряд |
| `features_question` | +5 | Вопрос о функциях |
| `integrations_question` | +5 | Вопрос об интеграциях |
| `price_question` | +5 | Вопрос о цене |
| `general_interest` | +3 | Общий интерес |
| `objection_no_need` | -25 | «Не нужно» |
| `rejection_soft` | -25 | Мягкий отказ |
| `objection_no_time` | -20 | «Нет времени» |
| `objection_price` | -15 | Возражение по цене |
| `objection_competitor` | -10 | Возражение «конкурент» |
| `objection_think` | -10 | Возражение «подумать» |
| `unclear_repeated` | -5 | Повторное «неясно» |
| `frustration` | -15 | Фрустрация |

---

## 8. Архитектура интеграции (высокоуровневая)

```
┌─────────────────────┐     ┌──────────────────────────┐     ┌──────────────────┐
│  Мессенджер-платформа│     │     API-Gateway          │     │   AI‑сервис      │
│  (WhatsApp/Telegram) │────▶│  (внешняя система)       │────▶│   (stateless)    │
│                     │◀────│                          │◀────│                  │
└─────────────────────┘     │  - auth & routing         │     │  - SalesBot      │
                            │  - session management     │     │  - Ollama LLM    │
┌─────────────────────┐     │  - bot/operator switch    │     │  - KB (in-memory)│
│   Оператор (UI)      │────▶│  - snapshot persistence   │     │  - Embeddings    │
│  - Перехватить       │     │  - config selection       │     │  - Reranker      │
│  - Продолжить       │     │  - deduplication          │     └──────────────────┘
│  - Просмотр истории │     │  - concurrency control    │
└─────────────────────┘     └────────────┬─────────────┘
                                         │
┌─────────────────────┐     ┌────────────▼─────────────┐     ┌──────────────────┐
│   Админ-панель       │     │       MongoDB             │     │     Ollama       │
│  - Конфигурации     │────▶│                          │     │  (Qwen3 14B)     │
│  - Feature Flags    │     │  - conversations          │     │                  │
│  - База знаний      │     │  - messages               │     │  GPU Server      │
│  - Мониторинг       │     │  - tenant_settings        │     └──────────────────┘
└─────────────────────┘     │  - operator_handoffs      │
                            └──────────────────────────┘
```

### 8.1 Компоненты для разработки

| Компонент | Что нужно создать | Приоритет |
|---|---|---|
| **API‑обёртка AI‑сервиса** | REST API поверх SalesBot (FastAPI), stateless | Критический |
| **MongoDB‑адаптер** | Хранилище: snapshots, messages, traces, tenant settings | Критический |
| **Webhook‑обработчик** | Приём сообщений от мессенджер-платформы | Критический |
| **Operator Router** | Маршрутизация бот/оператор + перехват/возврат | Критический |
| **Concurrency Control** | Очередь/lock для последовательной обработки сообщений в сессии | Критический |
| **Админ-панель** | UI для конфигураций (раздел 7) | Высокий |
| **Health Check** | Endpoint /health для мониторинга | Средний |

### 8.2 Точки интеграции в коде

| Компонент | Где | Назначение |
|---|---|---|
| `SalesBot` | `src/bot.py` | `process()` — обработка хода, `to_snapshot()` / `from_snapshot()` — сериализация |
| `ConfigLoader` | `src/config_loader.py` | Загрузка конфигурации из YAML по `config_name` + runtime override (`set_config_override()`) |
| LLM клиент | `src/llm.py` (`OllamaLLM`) | Можно заменить на другой клиент |
| Knowledge retriever | `src/knowledge/retriever.py` (`CascadeRetriever`) | FRIDA + BGE reranker |
| Decision trace | `src/decision_trace.py` | Формирование trace (теперь обязательный) |

---
