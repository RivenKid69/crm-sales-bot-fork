# Документация по проекту CRM Sales Bot для интеграции

> Документ предназначен для аналитика, составляющего ТЗ на интеграцию чат-бота
> в мессенджер-платформу (аналог Wazzup).

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
| 271 интент | Классификация намерений пользователя в 34 категориях |
| База знаний | 1 969 секций в 17 категориях (цены, продукты, оборудование, интеграции и т.д.) |
| Обработка возражений | 8 типов возражений, 120+ паттернов, фреймворки 4P's и 3F's |
| Lead scoring | Динамическая оценка лида (0–100) с температурой (cold/warm/hot/very_hot) |
| Анализ тона | 3-уровневый каскад: regex → FRIDA (semantic) → LLM; фрустрация 0–10 |
| Защитные механизмы | Конверсационный guard, stall detection, phase exhaustion, fallback 4 уровней |
| Decision tracing | Полная трассировка всех решений на каждом ходе |

### 1.2 Технологический стек

| Компонент | Технология |
|---|---|
| Язык | Python 3.10+ |
| LLM | Qwen3 14B через Ollama (localhost:11434) |
| Embeddings | ai-forever/FRIDA (Sentence Transformers) |
| Reranker | BAAI/bge-reranker-v2-m3 |
| Конфигурация | YAML (settings, flows, knowledge base, constants) |
| Тесты | ~235 файлов, 8 000+ тестов |
| Размер кодовой базы | ~80 000 строк кода, 160+ модулей (src/) |

### 1.3 Текущее состояние

Ядро бота поставляется как Python‑библиотека и CLI‑демо. В коде уже есть:
- **SessionManager** (кеш активных сессий, TTL‑очистка, загрузка snapshot только на cache miss)
- **Snapshot API** (`SalesBot.to_snapshot/from_snapshot`) + локальный буфер snapshot
- **TTL‑компакция истории** (HistoryCompactor) и правило «последние 4 сообщения берутся из внешней истории»
- **Multi‑config / multi‑flow** поддержка и защита от смешивания сессий через `client_id`

Чего нет (и это делает внешняя интеграция):
- HTTP API / REST эндпоинтов
- Прямого подключения к БД и мессенджерам (всё через callbacks)
- Глобального распределённого lock на несколько хостов (для single‑host есть локальный lock)

---

## 2. Требования к интеграции

### 2.1 Разделение ответственности

**Внешняя система (аналог Wazzup):**
- принимает входящие сообщения
- определяет `client_id`, `session_id` (chat/conversation), `flow_name`, `config_name`
- хранит историю сообщений и snapshots
- вызывает бота и принимает ответ

**CRM Sales Bot (ядро):**
- обрабатывает текст и держит состояние через `SessionManager`
- формирует snapshot и складывает его в локальный буфер
- выполняет TTL‑компакцию истории при простое
- выгружает пачку snapshot во внешнюю БД по правилу «после 23:00 — первый запрос»

### 2.2 Идентификация и изоляция

Минимальный набор идентификаторов:
- `client_id` — идентификатор клиента/тенанта (обязателен для изоляции)
- `session_id` — идентификатор диалога (conversation/chat)

`client_id` **всегда пишется внутрь snapshot**.  
При восстановлении, если `snapshot.client_id != expected client_id`, snapshot игнорируется.

### 2.3 Контракт хранения (внешняя БД/хранилище)

Ядро бота не подключается напрямую к БД. Интегратор предоставляет callbacks:

- `load_snapshot(session_id) -> Optional[Dict]`
- `save_snapshot(session_id, snapshot) -> None`
- `load_history_tail(session_id, n) -> List[Dict]` (последние `n` сообщений)

**Важно:** `save_snapshot` вызывается не сразу, а при вечерней выгрузке пачки.

### 2.4 Маршрутизация и конкуррентность

Рекомендуется sticky‑routing по `session_id` (consistent hashing или sticky‑cookie).
Даже при sticky‑routing возможны гонки — нужен lock на время обработки сообщения.

В ядре есть `SessionLockManager` на файловых lock‑ах (single‑host).  
Для multi‑host следует заменить его на Redis/PG advisory lock.

### 2.5 Хостинг и инфраструктура (ориентир)

| Параметр | Значение |
|---|---|
| LLM | Qwen3 14B через Ollama (требуется GPU‑сервер, ~9.3 GB VRAM) |
| Embedding‑модели | Локальные, загружаются при старте (~500 MB) |

### 2.6 Логирование

Structured‑логи идут в stdout (JSON/Readable через `LOG_FORMAT`).
При интеграции можно забирать логи напрямую или сделать отдельный Log Exporter.

### 2.7 Админ‑панель и оператор

Админ‑панель и операторские сценарии описаны ниже (разделы 5–6).  
Они не обязательны для запуска базовой интеграции.

---

## 3. API-контракт бота

### 3.1 Точка входа (SessionManager)

Рекомендуемый вход — `SessionManager`, который отвечает за кеш, TTL и снапшоты.

```python
from src.session_manager import SessionManager

manager = SessionManager(
    load_snapshot=load_snapshot,         # из вашей БД
    save_snapshot=save_snapshot,         # в вашу БД
    load_history_tail=load_history_tail  # последние 4 сообщения
)

bot = manager.get_or_create(
    session_id="chat-123",
    client_id="client-42",
    flow_name="spin_selling",
    config_name="tenant_alpha",
    llm=ollama_llm
)

result = bot.process(user_message="текст сообщения")
```

**Важно:** внешний воркер/cron должен вызывать `manager.cleanup_expired()` каждые 5–10 минут,
чтобы сработал TTL‑снапшот и компакция истории.

### 3.2 Входные данные (что бот ожидает)

На каждый ход бот получает **одну текстовую строку** — сообщение пользователя,
а внешняя система передаёт метаданные:

| Поле | Тип | Описание |
|---|---|---|
| `client_id` | `str` | Идентификатор клиента/тенанта |
| `session_id` | `str` | Идентификатор диалога |
| `flow_name` | `str` | Имя sales flow |
| `config_name` | `str` | Имя конфигурации клиента |

Восстановление диалога выполняет `SessionManager` через callbacks:
`load_snapshot()` и `load_history_tail()` — вручную собирать состояние не нужно.

### 3.3 Выходные данные (что бот возвращает)

Метод `process()` возвращает `Dict` со следующей структурой:

```python
{
    # === Ответ ===
    "response": str,                    # Текст ответа бота

    # === Классификация ===
    "intent": str,                      # Определённый интент (demo_request, objection_price, ...)
    "action": str,                      # Действие (continue_conversation, soft_close, ...)

    # === Состояние ===
    "state": str,                       # Текущее состояние FSM
    "initial_state": str,               # Состояние до обработки
    "spin_phase": str | None,           # Текущая фаза flow (SPIN/другая)
    "visited_states": List[str],        # Состояния, посещённые на этом ходе
    "is_final": bool,                   # Диалог завершён

    # === Тон и эмоции ===
    "tone": str | None,                 # Тон (neutral, frustrated, interested, ...)
    "frustration_level": int,           # Уровень фрустрации (0–10)

    # === Fallback ===
    "fallback_used": bool,              # Был ли использован fallback
    "fallback_tier": str | None,        # Tier fallback-а (fallback_tier_1/2/3, soft_close)

    # === Lead scoring ===
    "lead_score": int | None,           # Оценка лида (0–100)

    # === Возражения ===
    "objection_detected": bool,         # Обнаружено ли возражение

    # === CTA ===
    "cta_added": bool,                  # Добавлен ли Call-to-Action
    "cta_text": str | None,             # Текст CTA

    # === Дополнительно ===
    "options": List[str] | None,        # Варианты для disambiguation / fallback
    "decision_trace": Dict | None       # Полная трассировка решений (если tracing включён)
}
```

### 3.4 Snapshot lifecycle (как это работает)

1. **Активная сессия** живёт в кеше `SessionManager`. Snapshot не читается на каждое сообщение.
2. Если тишина > `TTL` (по умолчанию 1 час), внешний воркер вызывает `cleanup_expired()`:
   - создаётся snapshot
   - запускается компакция истории
   - snapshot кладётся в локальный буфер (`LocalSnapshotBuffer`)
3. После 23:00 **первый запрос** запускает batch‑flush:
   - все локальные snapshot выгружаются через `save_snapshot`
   - локальный буфер очищается

**Правило истории:** последние 4 сообщения не кладутся в snapshot  
и при восстановлении берутся через `load_history_tail(session_id, 4)`.

### 3.5 Переключение flow/config “на лету”

Если внешняя система присылает новый `flow_name` или `config_name` для активной
сессии, `SessionManager` пересоздаёт бота из snapshot текущего состояния и
поднимает новую конфигурацию/flow без потери состояния.

---

## 4. Модель данных для PostgreSQL (справочно)

Этот раздел — **референс**, а не обязательная схема.  
Внешняя система может хранить данные иначе, главное обеспечить callbacks:
`load_snapshot`, `save_snapshot`, `load_history_tail`.

### 4.1 Сущности для хранения

#### Таблица `conversations` — диалоги

| Поле | Тип | Описание |
|---|---|---|
| `id` | `UUID` PK | ID диалога |
| `user_external_id` | `VARCHAR` | ID пользователя из мессенджер-платформы |
| `status` | `ENUM` | `bot_active`, `operator_active`, `escalated`, `completed`, `paused` |
| `flow_name` | `VARCHAR` | Активная методология (spin_selling, bant, ...) |
| `current_state` | `VARCHAR` | Текущее состояние FSM |
| `current_phase` | `VARCHAR` | Текущая фаза flow (SPIN/другая) |
| `lead_score` | `INTEGER` | Текущий lead score (0–100) |
| `lead_temperature` | `VARCHAR` | cold / warm / hot / very_hot |
| `outcome` | `VARCHAR` | Итог: success, demo_scheduled, soft_close, rejected, abandoned, timeout, error |
| `collected_data` | `JSONB` | Собранные данные о клиенте |
| `bot_state_snapshot` | `JSONB` | Полный snapshot состояния бота (для возобновления) |
| `total_turns` | `INTEGER` | Количество ходов |
| `created_at` | `TIMESTAMP` | Время создания |
| `updated_at` | `TIMESTAMP` | Последнее обновление |
| `completed_at` | `TIMESTAMP` | Время завершения |

#### Таблица `messages` — сообщения

| Поле | Тип | Описание |
|---|---|---|
| `id` | `UUID` PK | ID сообщения |
| `conversation_id` | `UUID` FK | Ссылка на диалог |
| `turn_number` | `INTEGER` | Номер хода |
| `role` | `ENUM` | `user`, `bot`, `operator` |
| `content` | `TEXT` | Текст сообщения |
| `intent` | `VARCHAR` | Определённый интент (только для user) |
| `confidence` | `FLOAT` | Уверенность классификации |
| `extracted_data` | `JSONB` | Извлечённые данные (структурные поля) |
| `action` | `VARCHAR` | Действие бота |
| `state_before` | `VARCHAR` | Состояние FSM до обработки |
| `state_after` | `VARCHAR` | Состояние FSM после обработки |
| `tone` | `VARCHAR` | Определённый тон |
| `frustration_level` | `INTEGER` | Уровень фрустрации (0–10) |
| `fallback_used` | `BOOLEAN` | Был ли fallback |
| `fallback_tier` | `VARCHAR` | Tier fallback-а (`fallback_tier_1/2/3`, `soft_close`) |
| `objection_detected` | `BOOLEAN` | Обнаружено ли возражение |
| `lead_score_after` | `INTEGER` | Lead score после этого хода |
| `cta_added` | `BOOLEAN` | Добавлен ли CTA |
| `options` | `JSONB` | Варианты (disambiguation) |
| `created_at` | `TIMESTAMP` | Время сообщения |
| `response_time_ms` | `FLOAT` | Время генерации ответа |

#### Таблица `decision_traces` — трассировка решений

| Поле | Тип | Описание |
|---|---|---|
| `id` | `UUID` PK | ID записи |
| `conversation_id` | `UUID` FK | Ссылка на диалог |
| `message_id` | `UUID` FK | Ссылка на сообщение |
| `turn_number` | `INTEGER` | Номер хода |
| `trace_data` | `JSONB` | Полный decision trace (см. раздел 7.2) |
| `created_at` | `TIMESTAMP` | Время |

#### Таблица `operator_handoffs` — передачи бот ↔ оператор

| Поле | Тип | Описание |
|---|---|---|
| `id` | `UUID` PK | ID записи |
| `conversation_id` | `UUID` FK | Ссылка на диалог |
| `direction` | `ENUM` | `bot_to_operator`, `operator_to_bot`, `operator_intercept` |
| `reason` | `VARCHAR` | Причина передачи |
| `operator_id` | `VARCHAR` | ID оператора |
| `turn_number` | `INTEGER` | На каком ходе произошла передача |
| `bot_state_snapshot` | `JSONB` | Snapshot состояния бота на момент передачи |
| `created_at` | `TIMESTAMP` | Время |

#### Таблица `conversation_metrics` — метрики диалогов

| Поле | Тип | Описание |
|---|---|---|
| `id` | `UUID` PK | ID записи |
| `conversation_id` | `UUID` FK | Ссылка на диалог |
| `total_turns` | `INTEGER` | Общее количество ходов |
| `duration_seconds` | `FLOAT` | Длительность диалога |
| `outcome` | `VARCHAR` | Итог диалога |
| `final_lead_score` | `INTEGER` | Финальный lead score |
| `phase_distribution` | `JSONB` | Ходы по фазам `{situation: 3, problem: 2, ...}` |
| `intents_sequence` | `JSONB` | Последовательность интентов `[greeting, company_info, ...]` |
| `objection_count` | `INTEGER` | Количество возражений |
| `objections_resolved` | `INTEGER` | Разрешённых возражений |
| `fallback_count` | `INTEGER` | Количество fallback-ов |
| `fallback_by_tier` | `JSONB` | Fallback-и по tier `{tier_1: 2, tier_2: 1}` |
| `dominant_tone` | `VARCHAR` | Преобладающий тон |
| `tone_history` | `JSONB` | История тона `[{turn, tone, state}, ...]` |
| `lead_score_history` | `JSONB` | История lead score `[{turn, score, signal}, ...]` |
| `collected_data` | `JSONB` | Все собранные данные |
| `created_at` | `TIMESTAMP` | Время создания |

### 4.2 Snapshot состояния бота (bot_state_snapshot)

Для возобновления диалога после паузы или передачи от оператора сохраняется
полный snapshot. Формат соответствует текущей реализации `SalesBot.to_snapshot()`:

```json
{
  "version": "1.0",
  "conversation_id": "abc123",
  "client_id": "client-42",
  "timestamp": 1699999999.123,

  "flow_name": "spin_selling",
  "config_name": "tenant_alpha",

  "state_machine": {
    "state": "spin_problem",
    "current_phase": "problem",
    "collected_data": {
      "company_size": "50-100",
      "current_tools": "Excel",
      "business_type": "retail"
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
    }
  },

  "guard": {
    "turn_count": 5,
    "state_history": ["greeting", "spin_situation", "spin_problem"],
    "message_history": ["привет", "у нас магазин, 50 сотрудников"],
    "phase_attempts": {"greeting": 1, "spin_situation": 2, "spin_problem": 2},
    "frustration_level": 2,
    "intent_history": ["greeting", "company_info", "explicit_problem"],
    "last_intent": "explicit_problem",
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

  "fallback": { "total_count": 0, "tier_counts": {}, "state_counts": {} },
  "objection_handler": { "objection_attempts": {"PRICE": 1} },

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
    "turns": [ ... ],
    "episodic_memory": { "episodes": [], "max_episodes": 50 }
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
    "compacted_at": 1699999999.123,
    "compaction_version": "1.0",
    "llm_model": "qwen3:14b"
  },

  "last_action": "ask_current_tools",
  "last_intent": "explicit_problem",
  "last_bot_message": "Какую систему используете сейчас?",

  "metrics": { ... }
}
```

**Примечания:**
- `history` всегда пустой массив — последние 4 сообщения берутся из внешней истории.
- `client_id` обязателен для защиты от восстановления чужого снапшота.
- `guard` и `fallback` заменяют старые поля `guard_state` и `fallback_handler`.
- `_context_window_full` и `_signals_history_full` используются для точного восстановления.

---

## 5. Протокол передачи диалога (бот ↔ оператор)

### 5.1 Состояния диалога

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

### 5.2 Триггеры эскалации (бот → оператор)

Бот инициирует передачу оператору при:

| Триггер | Описание | Источник в коде |
|---|---|---|
| Явный запрос человека | Интенты из категории `escalation` (request_human, speak_to_manager, ...) | `EscalationSource` |
| Sensitive topics | Интенты из категории `sensitive` (legal/compliance/complaints) | `EscalationSource` |
| Фрустрация | Повторные интенты категории `frustration` (порог `frustration_threshold`, default=3) | `EscalationSource` |
| Повторные непонимания | `unclear` >= `misunderstanding_threshold` (default=4) | `EscalationSource` |
| High‑value + complex | `company_size >= 100` и intent ∈ {`custom_integration`, `enterprise_features`, `sla_question`} | `EscalationSource` |

Эскалация в коде проявляется как `action = "escalate_to_human"` и переход в
`state = "escalated"` (либо `entry_points.escalation` в конкретном flow).

### 5.3 Возврат диалога от оператора к боту

При возврате необходимо:
1. Загрузить `bot_state_snapshot` из таблицы `operator_handoffs`
2. Восстановить состояние `SalesBot` из snapshot
3. Изменить `status` в таблице `conversations` на `bot_active`
4. Продолжить обработку с восстановленного состояния

### 5.4 Перехват оператором

При перехвате:
1. Сохранить текущий `bot_state_snapshot`
2. Записать `operator_handoff` с `direction = operator_intercept`
3. Изменить `status` на `operator_active`
4. Все последующие сообщения идут оператору, а не боту

---

## 6. Scope админ-панели

Админ-панель управляет **всеми конфигурациями** бота. Ниже — полный перечень
конфигурационных областей.

### 6.1 Tier 1: Базовая конфигурация (для менеджеров/продажников)

#### 6.1.1 Выбор sales flow

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

Текущий flow задаётся в `settings.yaml → flow.active`.

#### 6.1.2 Feature Flags (60+ тогглов)

Тогглы сгруппированы по фазам:

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

#### 6.1.3 База знаний (Knowledge Base)

17 категорий, 1 969 секций. Каждая секция:

```yaml
sections:
  - topic: "Тарифы для малого бизнеса"
    priority: 8                         # 1-10, влияет на порядок выдачи
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

#### 6.1.4 Управление возражениями

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

Лимиты: `max_consecutive_objections`, `max_total_objections` (по персонам).

### 6.2 Tier 2: Продвинутая настройка (для тимлидов/продуктологов)

#### 6.2.1 Лимиты диалога

| Параметр | По умолчанию | Описание |
|---|---|---|
| `max_turns` | 25 | Максимум ходов в диалоге |
| `max_phase_attempts` | 3 | Максимум попыток в одной фазе |
| `max_same_state` | 4 | Максимум ходов в одном состоянии |
| `max_gobacks` | 2 | Максимум возвратов назад |
| `timeout_seconds` | 1800 | Таймаут диалога (30 мин) |
| `high_frustration_threshold` | 7 | Порог фрустрации для эскалации |

#### 6.2.2 Разнообразие ответов (diversity)

- **Запрещённые начала**: фразы, которые бот не должен использовать (монотонность)
- **Альтернативные начала**: по контексту (эмпатия, подтверждение, позитив)
- **Переходные фразы**: связки между блоками ответа
- **LRU-ротация**: не повторять одинаковые начала подряд

#### 6.2.3 Дедупликация вопросов

19 полей данных для трекинга (company_size, current_tools, pain_point и т.д.).
Бот не задаёт вопрос повторно, если данные уже собраны.

#### 6.2.4 Диалоговые политики (policy overlays)

5 политик, работающих поверх state machine:

| Политика | Триггер | Действие |
|---|---|---|
| `repair_mode` | Диалог застрял / зацикливание | Уточнить / предложить варианты |
| `objection_overlay` | Повторные возражения | Усилить аргументацию / эскалировать |
| `price_question_overlay` | Вопрос о цене | Гарантированно ответить с ценой |
| `breakthrough_overlay` | Позитивный сдвиг | Мягкий CTA |
| `conservative_overlay` | Низкая уверенность | Осторожный режим |

#### 6.2.5 Настройки LLM и поиска

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

### 6.3 Tier 3: Экспертная конфигурация (для разработчиков)

#### 6.3.1 Таксономия интентов

271 интент, каждый с атрибутами:

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

#### 6.3.2 Маппинг интент → действие

Переопределение действий для конкретных интентов:

```yaml
price_question → answer_with_pricing
demo_request → schedule_demo
contact_provided → collect_contact
```

#### 6.3.3 Порог disambiguator

| Параметр | Значение |
|---|---|
| `high_confidence` | 0.85 |
| `medium_confidence` | 0.65 |
| `low_confidence` | 0.45 |
| `min_confidence` | 0.30 |
| `gap_threshold` | 0.20 |
| `max_options` | 3 |
| `cooldown_turns` | 3 |

#### 6.3.4 Lead scoring сигналы

Положительные и отрицательные сигналы с весами:

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

## 7. Формат логирования

### 7.1 Структура логов

Логи формируются из `decision_trace` (возвращается `SalesBot.process()` при `enable_tracing`).
Выходной формат — **JSON-файл** с полной трассировкой каждого хода, аналогичный e2e-симуляциям.

### 7.2 Структура decision trace (на каждый ход)

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

  "objection": {
    "detected": false,
    "attempt_number": 0,
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

### 7.3 Файл отчёта по диалогу

Помимо JSON с decision traces, генерируется текстовый отчёт:

```
================================================================================
ОТЧЁТ ПО ДИАЛОГУ
ID: conv_abc123
Дата: 2026-02-04 12:30:45
================================================================================

ОБЩАЯ СТАТИСТИКА
  Ходов: 12
  Длительность: 45 сек
  Итог: success
  Lead Score: 75 (hot)
  Flow: spin_selling

ФАЗЫ ДИАЛОГА
  situation  ████████░░ 3 хода
  problem    ██████░░░░ 2 хода
  implication ████░░░░░░ 2 хода
  need_payoff ██████░░░░ 2 хода
  presentation ████░░░░░░ 2 хода
  close       ██░░░░░░░░ 1 ход

ВОЗРАЖЕНИЯ: 2 / 2 разрешены
  objection_price → reframe_value → resolved (ход 5)
  objection_think → feel_felt_found → resolved (ход 8)

FALLBACK: 0

ПОЛНЫЙ ДИАЛОГ
  [1] USER: Привет
      BOT: Добрый день! Расскажите...
      intent=greeting conf=0.98 state=greeting→spin_situation
  [2] USER: У нас магазин, 50 сотрудников
      BOT: Какую систему учёта используете сейчас?
      intent=company_info conf=0.91 state=spin_situation
  ...
================================================================================
```

---

## 8. Архитектура интеграции (высокоуровневая)

```
┌─────────────────────┐     ┌────────────────────┐     ┌──────────────┐
│  Мессенджер-платформа│     │    API-Gateway      │     │  CRM Sales   │
│  (аналог Wazzup)    │────▶│  (REST / Webhook)   │────▶│     Bot      │
│                     │◀────│                    │◀────│              │
│  WhatsApp/Telegram  │     │  - auth             │     │  - SalesBot  │
│  и др.              │     │  - routing           │     │  - Ollama    │
└─────────────────────┘     │  - bot/operator      │     │  - KB        │
                            │    switch            │     └──────┬───────┘
┌─────────────────────┐     └────────┬───────────┘            │
│   Админ-панель       │             │                        │
│   (кастомная)        │             │                        │
│                     │             ▼                        ▼
│  - Конфигурации     │     ┌────────────────────┐  ┌──────────────┐
│  - Feature Flags    │────▶│    PostgreSQL       │  │    Ollama     │
│  - База знаний      │     │                    │  │  (Qwen3 14B) │
│  - Мониторинг       │     │  - conversations    │  │              │
└─────────────────────┘     │  - messages          │  │  GPU Server  │
                            │  - decision_traces   │  │  Yandex      │
┌─────────────────────┐     │  - operator_handoffs │  └──────────────┘
│   Оператор (UI)      │     │  - metrics          │
│                     │────▶│  - configs           │
│  - Перехват диалога │     └────────────────────┘
│  - Возврат боту     │
│  - Просмотр истории │
└─────────────────────┘
```

### 8.1 Компоненты для разработки

| Компонент | Что нужно создать | Приоритет |
|---|---|---|
| **API-слой** | REST API поверх SalesBot (FastAPI) | Критический |
| **PostgreSQL-адаптер** | Персистентное хранилище + сериализация snapshot (бот, метрики, трассы) | Критический |
| **Webhook-обработчик** | Приём сообщений от мессенджер-платформы | Критический |
| **Operator Router** | Маршрутизация бот/оператор + перехват | Критический |
| **State Restoration** | Восстановление состояния бота из snapshot | Критический |
| **Админ-панель** | UI для всех конфигураций (раздел 6) | Высокий |
| **Config DB** | Хранение конфигураций в PostgreSQL | Высокий |
| **Log Exporter** | Выгрузка decision traces в файлы | Средний |
| **Health Check** | Endpoint /health для мониторинга | Средний |

### 8.2 Реальные точки интеграции в коде

Формальных портов `IContextStorage`/`IChannel` в коде нет (они упоминаются только в
`DESIGN_PRINCIPLES.md`). Интеграция делается через обёртку над `SalesBot` и
ручную сериализацию состояния.

| Компонент | Где | Примечание |
|---|---|---|
| `SalesBot` | `src/bot.py` | Единственная точка входа: `process()` |
| LLM клиент | `src/llm.py` (`OllamaLLM`) | Можно заменить на другой клиент |
| Knowledge retriever | `src/knowledge/retriever.py` (`CascadeRetriever`) | FRIDA + BGE reranker |
| Logger | `src/logger.py` | stdout JSON/Readable (через `LOG_FORMAT`) |
| Decision trace | `src/decision_trace.py` | Возвращается в `process()` при `enable_tracing` |

---

## 9. Открытые вопросы

| # | Вопрос | Влияние на ТЗ |
|---|---|---|
| 1 | Подтвердить провайдера/регион хостинга (Яндекс Cloud?) | Архитектура деплоя, комплаенс |
| 2 | GPU для Ollama — выделенный GPU-сервер или облачный LLM API? | Архитектура деплоя, стоимость |
| 3 | Ожидаемое кол-во одновременных диалогов? | Масштабирование, очереди |
| 4 | SLA на время ответа бота? | Нужен ли кеш, оптимизации |
| 5 | Бот инициирует диалог или только отвечает? | Webhook vs push |
| 6 | Нужны ли кнопки/quick replies в мессенджере? | Формат ответа |
| 7 | Как бот обрабатывает медиа (голос, фото, файлы)? | Расширение API |
| 8 | Нужны ли follow-up сообщения (бот пишет первым через N часов)? | Планировщик задач |
| 9 | Требования по 152-ФЗ (персональные данные)? | Хранение, шифрование |
| 10 | Один тенант или мультитенантность? | Архитектура БД |
| 11 | Нужна ли аналитика/дашборды (конверсия, метрики)? | BI-интеграция |
