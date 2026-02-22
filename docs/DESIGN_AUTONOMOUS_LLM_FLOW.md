# Design Document: Autonomous LLM Flow

> Коммиты-основа: `0766d13` (refactor autonomous policy to context signals and gate deterministic overrides) и `3966625` (Refine autonomous flow: context gating, normalization, and CTA restraint).

---

## 1. Проблема, которую решает рефакторинг

До рефакторинга система работала в парадигме **"код решает, LLM озвучивает"**:

- **Sources диктовали action** — PriceQuestionSource и FactQuestionSource напрямую выбирали шаблон ответа (`answer_with_pricing`, `answer_with_facts`) и проставляли HIGH priority, перекрывая решение LLM.
- **Overlay-политики** (repair, objection, price, breakthrough, conservative) в `DialoguePolicy` переписывали action после blackboard'а — ещё один слой детерминизма поверх уже детерминированного решения.
- **Hard override по счётчику** — в `AutonomousDecisionSource` после N последовательных stay-решений LLM принудительно переключался в следующую фазу, вне зависимости от контекста диалога.
- **Template routing ломал единство prompt'а** — в зависимости от intent, `generator.py` подменял `autonomous_respond` на `answer_with_pricing` / `handle_objection_*`, каждый со своим набором инструкций.

Результат: LLM генерировал ~60% ответов не через свой основной шаблон, overlay-политики срабатывали в ~35% ходов, ложные срабатывания fact-вопросов ~17%. Бот звучал непоследовательно — каждый ход мог прийти из разного prompt'а с разным "голосом".

## 2. Центральный принцип

**LLM — единственный decision-maker для содержания и тона ответа в автономных состояниях.**

Код не решает *что* и *как* говорить клиенту. Код отвечает за:
- **контекст** — собрать и передать LLM всё, что нужно для решения,
- **границы** — не дать выйти за рамки безопасности (не придумывать данные, не обещать невозможного),
- **инфраструктуру** — переходы между состояниями, сбор данных, терминальные условия.

## 3. Архитектурные принципы

### 3.1. Sources = context providers, не action-dictators

Sources (PriceQuestion, FactQuestion) в автономных состояниях:
- **Не предлагают action** через `propose_action()` с HIGH priority
- **Добавляют context signal** через `blackboard.add_context_signal()` — структурированное сообщение, которое попадает в decision prompt AutonomousDecisionSource

Context signal — это не команда, а информация: "клиент спрашивает о цене (тариф)" или "клиент просит факты о интеграциях". LLM видит это и сам решает: ответить на вопрос в рамках текущего этапа, перейти к следующему, или сделать что-то третье.

### 3.2. Один шаблон — один голос

В автономных состояниях `generator.py` всегда возвращает `autonomous_respond` (кроме greeting → `greet_back`). Нет template routing по intent — нет ситуации, когда price intent уводит в `answer_with_pricing` с другим набором инструкций.

Вся информация (факты о ценах, данные о продукте, контекст возражений) поступает через единые переменные основного шаблона:
- `{retrieved_facts}` — KB-факты, уже отобранные EnhancedRetrievalPipeline
- `{objection_instructions}` — тактика работы с возражением (4P/3F)
- `{collected_data}` / `{missing_data}` — что известно, что нет
- `{closing_data_request}` — что нужно собрать для терминального состояния
- `{address_instruction}` — как обращаться к клиенту

### 3.3. Overlay-политики отключены в автономном контексте

Все 5 overlay'ев в `DialoguePolicy` — repair, objection, price, breakthrough, conservative — возвращают `None` для autonomous-состояний. LLM достаточно компетентен, чтобы обработать возражение, ответить на вопрос о цене или сменить тактику без программной подсказки.

Overlay'и остаются активными для legacy-потоков (не-autonomous), где по-прежнему нужен жёсткий контроль.

### 3.4. Нет hard override по счётчику

Удалён механизм `stay_streak >= phase_exhaust_threshold → force transition`. LLM видит в decision prompt историю своих решений ("3 раза подряд решил остаться") и сам понимает, когда пора двигаться дальше.

Детерминистические safety-net'ы остались:
- **Terminal gate** — нельзя перейти в `payment_ready` без kaspi_phone и IIN
- **StallGuard** — жёсткий предел ходов в состоянии (последний рубеж, не оптимизационный)
- **ConversationGuard** — обнаружение зацикливания

### 3.5. Автономный контекст шире, чем `autonomous_*` состояния

Greeting-состояние в autonomous flow (`state == "greeting"`, `flow.name == "autonomous"`) — это тоже автономный контекст. Sources и overlay'и не должны срабатывать на первом ходу, когда клиент ещё только поздоровался.

`_is_autonomous_context()` в каждом Source и в DialoguePolicy проверяет оба условия: и `state.startswith("autonomous_")`, и greeting в автономном flow.

### 3.6. Action normalization на выходе

В `bot.py` после resolve — если action не входит в список структурных (guard, stall, escalation), он нормализуется в `autonomous_respond`. Это страховка: даже если какой-то Source прорвался с нестандартным action, pipeline всё равно пойдёт через единый шаблон.

Структурные action'ы, которые проходят без нормализации:
```
ask_clarification, guard_offer_options, guard_rephrase, guard_skip_phase,
guard_soft_close, stall_guard_eject, stall_guard_nudge,
redirect_after_repetition, escalate_repeated_content
```

### 3.7. CTA — только в closing-like состояниях

CTA (Call-To-Action) в автономном flow добавляется только в `{autonomous_closing, close, soft_close, success}`. В discovery/qualification/presentation CTA выглядит навязчиво и режет доверие.

Если `question_mode == "suppress"` (response directives определили, что вопрос не нужен), CTA тоже не добавляется.

## 4. Поток данных в автономном ходе

```
User message
    │
    ▼
LLMClassifier → intent + secondary_intents
    │
    ▼
Blackboard.begin_turn() → ContextSnapshot (frozen)
    │
    ▼
Sources evaluate sequentially:
    ├─ PriceQuestionSource → add_context_signal(price_intent_detected)
    ├─ FactQuestionSource  → add_context_signal(fact_requested)
    ├─ IntentPatternGuard  → skip (autonomous)
    ├─ PhaseExhaustedSource → skip (autonomous)
    └─ AutonomousDecisionSource:
         ├─ reads context_signals from blackboard
         ├─ builds decision prompt (state + goal + signals + history)
         ├─ LLM decides: {stay | transition to X}
         ├─ terminal gate: blocks if missing required data
         └─ proposes action=autonomous_respond + optional transition
    │
    ▼
Resolver picks winning action (usually autonomous_respond @ NORMAL)
    │
    ▼
DialoguePolicy.maybe_override():
    └─ all overlays return None for autonomous context
    │
    ▼
bot.py action normalization:
    └─ non-structural action → autonomous_respond
    │
    ▼
ResponseGenerator._resolve_template_key():
    └─ autonomous flow → always "autonomous_respond" (except greeting)
    │
    ▼
ResponseGenerator._build_autonomous_variables():
    ├─ {retrieved_facts} ← EnhancedRetrievalPipeline
    ├─ {collected_data}, {missing_data}
    ├─ {address_instruction} ← one-time name ask logic
    ├─ {objection_instructions} ← 4P/3F if intent is objection
    ├─ {closing_data_request} ← terminal requirements
    ├─ {do_not_repeat_responses} ← anti-repetition
    ├─ {language_instruction}, {stress_instruction}
    └─ all injected into autonomous_respond template
    │
    ▼
Qwen generates response through single unified prompt
    │
    ▼
CTA gate: only in closing-like states
    │
    ▼
Final response to client
```

## 5. Как улучшать качество диалога

Правильная парадигма — **промпт-инжиниринг и контекстная подготовка**:

| Что улучшить | Где менять | Чего НЕ делать |
|---|---|---|
| Тон, стиль ответов | `prompts.yaml` → `autonomous_respond` template | Не создавать новые action'ы с отдельными шаблонами |
| SPIN-фазы, цели этапов | `states.yaml` → `goal` для каждого состояния | Не добавлять rule-based переходы |
| Работа с возражениями | `generator.py` → `{objection_instructions}` | Не добавлять overlay в DialoguePolicy |
| Ответы на вопросы о цене | KB data (`knowledge/data/*.yaml`) + EnhancedRetrievalPipeline | Не маршрутизировать в отдельный template |
| Запрос данных (имя, IIN) | `generator.py` → `_build_address_instruction()`, `{closing_data_request}` | Не хардкодить fast-track'и в Sources |
| Галлюцинации | `prompts.yaml` → "КРИТИЧЕСКИЕ ПРАВИЛА" секция | Не добавлять keyword-based фильтры |
| Повторяющиеся ответы | `{do_not_repeat_responses}` переменная + content repetition guard | Не блокировать intent'ы детерминистически |

## 6. Границы рефакторинга — что осталось без изменений

- **6-фазный SPIN FSM** (`discovery → qualification → presentation → objection_handling → negotiation → closing`) — структура этапов не менялась
- **Safety guards** (StallGuard, ConversationGuard) — остались как hard limits
- **Terminal gate** — детерминистическая проверка required data перед переходом
- **Blackboard как информационный слой** — архитектура Sources → Resolver не менялась, поменялось содержание contribute()
- **EnhancedRetrievalPipeline** — message-driven KB retrieval остался без изменений
- **Детерминистическая валидация данных** (ExtractionValidator, DataExtractor) — неизменна
- **Legacy flows** (не-autonomous) — overlay'и и routing работают как раньше

## 7. Метрики (10 диалогов, baseline vs after)

| Метрика | До | После | Интерпретация |
|---|---|---|---|
| Terminal state rate | 30% | 40% | +10% — LLM доводит больше диалогов до конца |
| Template override | 60.3% | 16.1% | -44pp — LLM решает через единый шаблон |
| Overlay activations | 34.6% | 0% | Полностью убраны для autonomous |
| False fact trigger | 16.7% | 0% | Stale carryover защищён |
| False price trigger | 0% | 0% | Было ок, осталось ок |
| SPIN coverage | 41.4% | 44.3% | +3pp — чуть больше фаз проходится |
| Avg turns to terminal | 6.7 | 9.0 | +2.3 хода — регрессия, LLM тщательнее |

## 8. Антипаттерны — чего избегать

1. **Добавлять Sources с HIGH priority в autonomous** — это откат к "код решает". Sources в autonomous = context signals only.
2. **Добавлять overlay'и в DialoguePolicy для autonomous** — overlay'и отключены сознательно.
3. **Добавлять fast-track'и и short-circuit'ы** — код не должен "помогать" LLM принимать решения быстрее. LLM видит контекст и принимает решения сам.
4. **Создавать новые шаблоны для отдельных intent'ов** — один шаблон, один голос. Вариативность через переменные, не через template routing.
5. **Хардкодить keyword patterns для routing** — если pattern нужен, он должен быть в classifier, а результат — в intent, а intent — в context signal для LLM.
6. **Считать "стоит" / "работает" надёжными keyword-маркерами** — омонимы в русском языке требуют контекстных паттернов, а не голых keyword match'ей.

## 9. Одно предложение

Система качества диалога строится на том, что LLM получает хорошо подготовленный контекст (KB-факты, данные клиента, цель этапа, история решений) и генерирует ответ через единый шаблон — а код обеспечивает безопасность, инфраструктуру переходов и сбор данных, но не вмешивается в содержание ответа.
