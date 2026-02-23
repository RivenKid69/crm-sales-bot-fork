# Design Document: Autonomous LLM Flow (Current Architecture)

> Актуализировано после коммитов `5d2831c` и `a3f4187` (февраль 2026).  
> Этот документ описывает состояние "как есть" в коде, а не исходный план.

---

## 1. Контекст и текущий статус

В автономном flow внедрены архитектурные изменения из плана P2–P6.  
P1 (merged decision+response в одном LLM вызове) реализован технически, но **принудительно выключен kill-switch'ем** из-за регрессии по конверсии.

Ключевой принцип остался прежним:
- LLM определяет содержимое ответа и обычно определяет переходы между фазами.
- Код держит safety-границы, терминальные условия и инфраструктуру пайплайна.

---

## 2. Что реально изменено в архитектуре

### 2.1. P3: lifecycle decision history (утечки/потери закрыты)

Реализовано в `src/blackboard/sources/autonomous_decision.py`:
- `AutonomousDecisionRecord.to_dict()` / `from_dict()`
- `AutonomousDecisionSource.decision_history`
- `AutonomousDecisionSource.restore_history()`
- `AutonomousDecisionSource.reset()`

Интеграция snapshot/reset:
- `src/blackboard/orchestrator.py`: `DialogueOrchestrator.reset()`
- `src/bot.py`: вызов `self._orchestrator.reset()` в `reset()`
- `src/bot.py`: сериализация `autonomous_decision_history` в `to_snapshot()`
- `src/bot.py`: восстановление history в `from_snapshot()`

Итог: история решений теперь корректно живёт между `to_snapshot()/from_snapshot()` и очищается между диалогами.

### 2.2. P4: SafeDict больше не скрывает критичные пропуски

В `src/generator.py` перед рендером шаблона добавлена проверка:
- `CRITICAL_TEMPLATE_VARS = {"system", "user_message", "history", "retrieved_facts"}`
- warning-лог при отсутствии/пустоте критичной переменной

`SafeDict.__missing__` сохранён (для мягкой деградации), но критичные дыры теперь наблюдаемы в логах.

### 2.3. P5: state-gated rules дедуплицированы и ограничены

Логика вынесена в `src/generator_autonomous.py`:
- правила стали `List[Tuple[priority, text]]`
- cap: `MAX_GATED_RULES = 5`
- сортировка по приоритету + обрезка
- форматирование фиксировано (`rule[1]`)

Содержательные изменения:
- объединён duplicate блок no-contact в HARD/SOFT
- `COMPARISON` и `INTERRUPTION` теперь взаимоисключающие
- `EXIT/CONTRACT` умеет инлайнить hard no-contact формат
- удалены дублирующие строки из автономного prompt template (`prompts.yaml`)

### 2.4. P2: лимиты размера prompt/KB

Лимиты синхронизированы:
- `src/knowledge/autonomous_kb.py`: `MAX_KB_CHARS = 25_000`
- `src/settings.yaml`: `enhanced_retrieval.max_kb_chars: 25000`

Дополнительно в `src/generator.py`:
- safety-truncation facts до ~25K для autonomous
- предупреждение в логах при обрезке
- `MAX_PROMPT_CHARS = 35_000` как guardrail-константа

Итог: prompt-budget стал предсказуемее, а runaway-context режется раньше.

### 2.5. P6: декомпозиция `generator.py`

Создан `src/generator_autonomous.py` и в него вынесены:
- автономные константы
- сбор state-gated правил
- contact-boundary helpers
- address/language/stress инструкции
- форматирование client card и post-boundary helper-функции

`src/generator.py` теперь в основном делегирует автономную логику в extracted module и делает re-export констант для backward compatibility.

Итог: меньшая связность, проще ревью/тестировать автономный слой отдельно.

### 2.6. P1: merged call реализован, но отключён

Что реализовано:
- `src/llm.py`: `generate_merged()` (structured, temp=0.3, num_predict=1024)
- `src/blackboard/sources/autonomous_decision.py`:
  `AutonomousDecisionAndResponse`, merged prompt, merged path в `contribute()`
- `src/blackboard/blackboard.py`: `_response_context`, `_pre_generated_response`
- `src/generator.py`: `prepare_response_context()` и `post_process_only()`
- `src/bot.py`: pre-generated intercept path + воспроизведение side effects

Что добавлено после регрессии:
- merged-mode stabilizer для `contact_provided` (детерминированный fast-path к terminal, когда данных достаточно)

Текущий production-статус:
- `src/feature_flags.py`: `FORCED_DISABLED = {"merged_autonomous_call"}`
- `flags.is_enabled("merged_autonomous_call")` всегда `False` даже при env/runtime override

---

## 3. Текущий поведенческий контракт autonomous flow

### 3.1. Переходы и safety

В `AutonomousDecisionSource` сейчас одновременно действуют:
- LLM-driven переходы по decision prompt
- terminal gates (`payment_ready`/`video_call_scheduled`) по required data
- payment-context guard (не финализировать путь оплаты без IIN, если не было явного отказа/дефера)
- deterministic streak override (3 stay подряд: objection-streak -> `soft_close`, иначе продвижение по фазе)

Это не "чисто LLM без детерминизма": автономный режим гибридный, с жёсткими safety-рамками.

### 3.2. Генерация ответа

- В autonomous-контексте ответ идёт через единый template family (`autonomous_respond` / `continue_current_goal`)
- Контент-инструкции собираются из:
  - layer-1 `SAFETY_RULES_V2`
  - layer-2 `state_gated_rules` (приоритет/кап)
  - KB facts + history + collected/missing + directives
- Перед рендером проверяются `CRITICAL_TEMPLATE_VARS`

### 3.3. Policy overlays

`DialoguePolicy` overlays (`repair/price/objection/breakthrough/conservative`) по-прежнему abstain в autonomous-контексте.  
Для non-autonomous flow поведение не менялось.

---

## 4. Поток данных (as-built)

```
User message
  -> классификация intent/secondary
  -> Blackboard.begin_turn()
  -> Sources (context signals + guards + AutonomousDecisionSource)
  -> Resolver (action + transition)
  -> DialoguePolicy (autonomous: overlays mostly abstain)
  -> bot action normalization (non-structural -> autonomous_respond)
  -> ResponseGenerator (KB + variables + rules)
  -> boundary validation / CTA gating
  -> final response
```

Если когда-либо будет снова включён merged path:
- bot сначала готовит `response_context`
- decision source может вернуть `pre_generated_response`
- bot пускает ответ через `post_process_only()` и применяет side effects вручную

---

## 5. Результаты ручных стресс-прогонов (10 сложных диалогов)

Источник: `scripts/run_manual_direct_stress10.py` (без симулятора).

| Прогон | elapsed_sec | terminal_rate (payment/video) | avg_turns_all |
|---|---:|---:|---:|
| baseline (`before_codex_plan6`) | 253.27 | 80% | 4.7 |
| после интеграции с merged ON | 251.32 | 10% | 4.8 |
| после интеграции с merged OFF | 246.45 | 70% | 4.7 |
| после P1 stabilizer, merged ON | 247.34 | 40% | 4.7 |

Вывод:
- P1 в текущей реализации не достигал приемлемой конверсии, даже после стабилизатора.
- Поэтому принят operational decision: держать merged path выключенным принудительно.
- P2/P3/P4/P5/P6 остаются в коде и считаются рабочими.

---

## 6. Операционные правила

1. `merged_autonomous_call` считается экспериментальным и заблокирован kill-switch'ем.
2. Любое повторное включение P1 требует:
   - снятия `merged_autonomous_call` из `FORCED_DISABLED`
   - обязательного прогона manual stress-10 и сравнения с baseline по terminal_rate
3. Документ фиксирует фактическую архитектуру; при изменении kill-switch или decision contract обновляется в том же PR.

---

## 7. Ограничения и дальнейшие шаги

- Известный вне-скоуп issue: порядок инициализации `do_not_repeat_responses` (отдельный backlog).
- Для объективной оценки P2/P5 нужен отдельный telemetry отчёт по размерам prompt и частоте срабатывания rule-cap (а не только terminal-rate).
- Для P1 нужен отдельный redesign merged prompt/decision contract; текущий вариант не проходит quality gate.
