# Changelog — последние 69 коммитов

Хронологически от новейшего к старейшему.

---

## [49a1e4a] fix: deep audit autonomous_closing — 5 fundamental fixes

**Затронутые файлы:** `src/blackboard/models.py`, `src/blackboard/orchestrator.py`, `src/blackboard/sources/autonomous_decision.py`, `src/blackboard/sources/price_question.py`, `src/classifier/extractors/data_extractor.py`, `src/classifier/extractors/extraction_validator.py`, `src/conditions/state_machine/contact_validator.py`, `src/generator.py`, `src/yaml_config/templates/autonomous/prompts.yaml`

**Описание:** Глубокий аудит закрывающего состояния `autonomous_closing`. Пять фундаментальных исправлений: корректная проверка наличия данных перед переходом в terminal state, исправление `contact_validator`, устранение некорректного срабатывания `PriceQuestionSource` в closing-контексте, расширение `extraction_validator` для KZ-форматов, инъекция `{closing_data_request}` в промпт генератора когда обязательные поля не заполнены.

---

## [932a8e7] feat: terminal states payment_ready + video_call_scheduled (10/10 e2e pass)

**Затронутые файлы:** `scripts/e2e_terminal_states.py` (новый), `src/blackboard/sources/autonomous_decision.py`, `src/blackboard/sources/data_collector.py`, `src/classifier/extractors/data_extractor.py`, `src/classifier/extractors/extraction_validator.py`, `src/classifier/llm/prompts.py`, `src/classifier/llm/schemas.py`, `src/generator.py`, `src/simulator/client_agent.py`, `src/yaml_config/flows/_base/states.yaml`, все `flow.yaml` (20 шт.)

**Описание:** Реализованы два терминальных состояния: `payment_ready` (сбор kaspi_phone + IIN до перехода) и `video_call_scheduled` (сбор contact_info, preferred_call_time — опционально). Добавлены `kaspi_phone` и `iin` в `ExtractedData` (schemas.py), в LLM-промпт-гайд (prompts.py), в `DataExtractor` (авто-копирование KZ-телефона в kaspi_phone) и в `ExtractionValidator` (`_validate_kaspi_phone`, `_validate_iin`). E2E-скрипт `e2e_terminal_states.py`: 303 строки, 10/10 pass.

---

## [1adea7d] fix: block close dominance over terminal states in autonomous_closing

**Затронутые файлы:** `src/blackboard/sources/autonomous_decision.py`, `src/blackboard/sources/stall_guard.py`, `src/yaml_config/flows/autonomous/states.yaml`

**Описание:** `AutonomousDecisionSource` больше не перезаписывает действие terminal state, если оно уже выставлено (`payment_ready` / `video_call_scheduled`). `StallGuard` также блокирован в терминальных состояниях, чтобы не инициировать soft_close поверх завершённой сделки.

---

## [c126141] feat: two distinct terminal states for autonomous closing flow

**Затронутые файлы:** `src/blackboard/sources/autonomous_decision.py`, `src/bot.py`, `src/metrics.py`, `src/simulator/metrics.py`, `src/yaml_config/constants.py`, `src/yaml_config/constants.yaml`, `src/yaml_config/flows/_base/states.yaml`, `src/yaml_config/flows/autonomous/states.yaml`

**Описание:** Введены два отдельных терминальных состояния вместо единого `closed`. Определены в `constants.yaml` как `TERMINAL_STATES`. `bot.py` распознаёт оба и формирует соответствующий ответ. Метрики симулятора обновлены для учёта обоих terminal state.

---

## [6f85a71] feat: universal closed-loop feedback system (10-step plan)

**Затронутые файлы:** `scripts/e2e_feedback_loop_check.py` (новый), `src/blackboard/sources/fact_question.py`, `src/blackboard/sources/price_question.py`, `src/conditions/policy/context.py`, `src/context_envelope.py`, `src/context_window.py`, `src/dialogue_policy.py`, `src/yaml_config/constants.py`, `src/yaml_config/constants.yaml`

**Описание:** Реализована универсальная система закрытых петель обратной связи. `ContextEnvelope` расширен полями для отслеживания повторных вопросов и ответных паттернов. `ContextWindow` получил методы детекции stale-интентов. `dialogue_policy.py` интегрирован с новыми сигналами. E2E скрипт проверки 261-строчный с 10-шаговым планом тестирования.

---

## [602610d] fix(kb): neutralize operator-voice facts to prevent hallucinations

**Затронутые файлы:** `src/knowledge/data/integrations.yaml`, `src/knowledge/data/pricing.yaml`, `src/knowledge/data/promotions.yaml`, `src/knowledge/data/regions.yaml`, `src/knowledge/data/support.yaml`, `src/knowledge/data/tis.yaml`

**Описание:** Переформулировка всех KB-фактов из "голоса оператора" ("мы предлагаем", "наши клиенты") в нейтральный третьелично-описательный стиль. Устраняет источник промпт-инъекций в LLM, где факты с "мы" заставляли модель говорить от имени компании непредсказуемо.

---

## [098b9fd] fix: replace CRM brand with Wipon POS/ТИС across all prompts and configs

**Затронутые файлы:** `src/classifier/llm/prompts.py`, `src/config.py`, `src/yaml_config/constants.yaml`, все 20 `flow.yaml`, `src/yaml_config/templates/_base/prompts.yaml`, `src/yaml_config/templates/consultative/prompts.yaml`

**Описание:** Глобальная замена брендинга: "CRM" → "Wipon POS/ТИС" во всех промптах, конфигах и flow-файлах. Исправляет контекстную ошибку — бот позиционировал продукт как CRM, хотя Wipon является POS/ТИС-системой для казахстанского ритейла.

---

## [0c41043] feat: hallucination prevention — layered grounding & deterministic escalation

**Затронутые файлы:** `src/config.py`, `src/generator.py`, `src/response_boundary_validator.py`, `src/yaml_config/templates/_base/prompts.yaml`, `src/yaml_config/templates/autonomous/prompts.yaml`, `tests/test_hallucination_guard.py` (325 строк)

**Описание:** Многоуровневая система предотвращения галлюцинаций. `ResponseBoundaryValidator` расширен слоями заземления. Генератор получил детерминированный эскалационный путь когда KB-данные отсутствуют. Промпты ужесточены правилами провенанса. 325-строчные тесты проверяют 15+ сценариев.

---

## [7bc31fe] fix: address 7 issues found in simulator self-review

**Затронутые файлы:** `src/simulator/client_agent.py`, `src/simulator/noise.py`

**Описание:** Устранение 7 дефектов найденных при self-review симулятора: некорректная генерация реплик в отдельных persona-ветках, баги в функции добавления казахского шума, краевые случаи в стартовых репликах.

---

## [377dba1] feat(simulator): ground personas in real Wipon POS dialogs

**Затронутые файлы:** `src/simulator/client_agent.py`, `src/simulator/kb_questions.py` (новый), `src/simulator/noise.py` (новый), `src/simulator/personas.py`

**Описание:** Расширение симулятора с 16 до 21 персоны (+ready_buyer, kazakh_speaker, suspicious_buyer, frustrated_waiter, niche_business). Все персоны переписаны на основе реальных диалогов Wipon POS. `noise.py`: `add_kazakh_noise()` — подстановка казахских приветствий, да→иә, рахмет. `kb_questions.py`: банк реальных вопросов из KB для генерации реплик клиента. KZ-формат телефонов (87xxx/+77xxx), 70% шанс телефона vs email.

---

## [d6c6816] fix: detect_repeated_question ignores stale price intent on topic change (BUG #4)

**Затронутые файлы:** `src/context_window.py`, `tests/test_nonsequitur_root_causes.py`

**Описание:** Исправление BUG #4: `detect_repeated_question` в `ContextWindow` теперь не возвращает `price_question` как repeated если текущее сообщение не содержит ценовых сигналов. Предотвращает ситуацию: пользователь сменил тему → stale `repeated_question=price_question` из предыдущих ходов → `PriceQuestionSource` срабатывал на нерелевантные сообщения.

---

## [bd1d149] fix: remove homonym keywords from secondary intent detection (BUG: стоит/давайте)

**Затронутые файлы:** `src/classifier/secondary_intent_detection.py`, `src/yaml_config/constants.yaml`, `tests/test_nonsequitur_root_causes.py`, `tests/test_secondary_intent_homonym_fixes.py` (355 строк, новый)

**Описание:** Удалены омонимы `"стоит"` и `"давайте"` из `price_question.keywords`. Слово "стоит" в значении "следует/worth" ("не стоит тратить время") ложно тригерило `secondary_intent=price_question`. Оставлены только контекстные паттерны `r"сколько\s+стоит"`. Добавлены 401+355 строк тестов на омонимы и несекводурные цепочки.

---

## [ae00986] fix: objection-driven hard override routes to soft_close (BUG #7)

**Затронутые файлы:** `src/blackboard/sources/autonomous_decision.py`, `tests/test_sources_autonomous_decision.py` (167 строк)

**Описание:** При жёстком возражении (hard objection) `AutonomousDecisionSource` теперь маршрутизирует в `soft_close` вместо продолжения закрытия. Исправляет баг #7 где агрессивное давление на закрытие при явном отказе клиента усугубляло ситуацию.

---

## [3989de1] fix: broken record — wire do_not_repeat_responses from memory to LLM prompt (BUG #3)

**Затронутые файлы:** `src/generator.py`, `src/yaml_config/templates/_base/prompts.yaml`, `src/yaml_config/templates/autonomous/prompts.yaml`, `tests/test_broken_record_fix.py` (276 строк)

**Описание:** Баг #3 — "заезженная пластинка": список `do_not_repeat_responses` из памяти диалога не передавался в LLM-промпт. Генератор теперь форматирует и инъектирует эти запреты в секцию промпта. Промпт-шаблоны обновлены под новую переменную. 276-строчные тесты.

---

## [8b51edf] fix: question density dedup bug + e2e question suppression tests (BUG #9)

**Затронутые файлы:** `src/bot.py`, `src/context_envelope.py`, `tests/e2e_question_suppression.py` (1421 строка, новый), `tests/test_question_suppression.py`

**Описание:** Исправление дедупликации в подсчёте плотности вопросов (`question_density`): счётчик дублировал вопросы из одного хода. `ContextEnvelope` получил исправленную логику. Добавлен масштабный e2e-тест (1421 строка) для системы подавления вопросов.

---

## [db7a342] fix: question suppression — 3-level system with 5 defensive layers (BUG #9)

**Затронутые файлы:** `src/config.py`, `src/context_envelope.py`, `src/generator.py`, `src/response_directives.py`, `src/yaml_config/constants.py`, `src/yaml_config/constants.yaml`, `src/yaml_config/templates/_base/prompts.yaml`, шаблоны bant/challenger/solution/spin_selling, `tests/test_question_suppression.py` (354 строки)

**Описание:** Баг #9 — бот задавал несколько вопросов подряд нарушая SPIN-методологию. Реализована трёхуровневая система: (1) счётчик вопросов в `ContextEnvelope`, (2) директива `suppress_question` в `ResponseDirectives`, (3) хард-блок в промпте генератора. Пять защитных слоёв против прорыва.

---

## [1d56b72] fix: autonomous flow forgets client facts — format collected_data + add missing fields

**Затронутые файлы:** `src/classifier/extractors/data_extractor.py`, `src/classifier/llm/prompts.py`, `src/classifier/llm/schemas.py`, `src/generator.py`, `src/yaml_config/constants.yaml`, `src/yaml_config/templates/autonomous/prompts.yaml`

**Описание:** Автономный флоу "забывал" факты о клиенте в середине диалога. `collected_data` не форматировался и не передавался в промпт. Генератор дополнен форматированием собранных данных (`company_name`, `contact_name`, `city`, `business_type` и др.). LLM-схема и промпт-гайд расширены недостающими полями.

---

## [024f471] test: add full e2e audit for Enhanced Autonomous Retrieval (200 queries, 100% accuracy)

**Затронутые файлы:** `tests/e2e_200_queries.py` (608 строк), `tests/e2e_audit_results.json`, `tests/e2e_audit_results_200.json`, `tests/e2e_full_pipeline_audit.py` (320 строк), `tests/test_enhanced_retrieval_e2e.py` (1523 строки)

**Описание:** Полный e2e-аудит системы Enhanced Autonomous Retrieval: 200 запросов, 100% точность по категориям KB. Три отдельных аудит-скрипта, результаты сохранены в JSON. Тест-файл 1523 строки охватывает все маршруты CategoryRouter.

---

## [9b65178] fix: remove silent fallback in CascadeRetriever + simplify autonomous retrieval

**Затронутые файлы:** `docs/ARCHITECTURE.md`, `docs/KNOWLEDGE.md`, `docs/SETTINGS.md`, `src/feature_flags.py`, `src/generator.py`, `src/knowledge/retriever.py`, `src/settings.yaml`, тесты (упрощение)

**Описание:** `CascadeRetriever` ранее молча возвращал пустой результат при провале всех уровней. Теперь логирует ошибку явно. Код генератора упрощён — убраны избыточные ветки fallback. Флаги feature_flags сокращены. Документация синхронизирована с кодом.

---

## [171aa50] docs: update architecture docs with style separation and enhanced retrieval

**Затронутые файлы:** `docs/ARCHITECTURE.md`, `docs/CLASSIFIER.md`, `docs/DESIGN_PRINCIPLES.md`, `docs/KNOWLEDGE.md`, `docs/SETTINGS.md`

**Описание:** Обновление пяти архитектурных документов: добавлены разделы о слое разделения стилей (`StyleModifierDetection`), Enhanced Retrieval Pipeline (CategoryRouter, RRF fusion, query rewriting). Документация теперь точно отражает runtime-поведение системы.

---

## [d7a2ded] feat: add style modifier separation layer (semantic intent / style split)

**Затронутые файлы:** `src/bot.py`, `src/classifier/refinement_layers.py`, `src/classifier/refinement_pipeline.py`, `src/classifier/secondary_intent_detection.py`, `src/classifier/style_modifier_detection.py` (новый, 196 строк), `src/classifier/unified.py`, `src/feature_flags.py`, `src/generator.py`, `src/personalization/result.py`, `src/yaml_config/constants.py/.yaml`, тесты (957 строк суммарно)

**Описание:** Выделен отдельный слой детекции стилевых модификаторов (`StyleModifierDetection`). Классификатор теперь разделяет семантическое намерение (что хочет клиент) и стилевой запрос (как отвечать — кратко/подробно/формально). Генератор использует `style_modifier` независимо от intent-маршрутизации.

---

## [0f484af] fix: enhance autonomous retrieval stability and correctness

**Затронутые файлы:** `src/classifier/disambiguation_engine.py`, `src/generator.py`, `src/knowledge/enhanced_retrieval.py`, тесты

**Описание:** Стабилизация `EnhancedRetrievalPipeline`: исправлены краевые случаи в `DisambiguationEngine` при неоднозначных запросах, улучшена логика выбора категории в CategoryRouter, добавлена дополнительная валидация результатов RRF-фьюжна.

---

## [4f583b7] test: add deep coverage for enhanced autonomous retrieval

**Затронутые файлы:** `tests/test_enhanced_retrieval_deep.py` (432 строки, новый)

**Описание:** Глубокое покрытие тестами `EnhancedRetrievalPipeline`: 432 строки, покрывают CategoryRouter (все категории KB), query rewriting, RRF fusion, state backfill, граничные случаи пустых и многокатегорийных запросов.

---

## [7e570d6] feat: add enhanced autonomous retrieval pipeline

**Затронутые файлы:** `src/feature_flags.py`, `src/generator.py`, `src/knowledge/enhanced_retrieval.py` (508 строк, новый), `src/settings.yaml`, `tests/test_enhanced_retrieval.py` (543 строки)

**Описание:** Реализован `EnhancedRetrievalPipeline`: CategoryRouter определяет категорию KB по тексту сообщения → LLM переформулирует запрос → RRF-фьюжн объединяет результаты из нескольких категорий → state backfill добавляет контекстные факты. Заменяет наивный text-search подход.

---

## [7d3b74f] fix: implement BUG #4 objection metrics chain and tests

**Затронутые файлы:** `src/blackboard/sources/objection_guard.py`, `src/blackboard/sources/objection_return.py`, `src/classifier/refinement_layers.py`, `src/intent_tracker.py`, `src/simulator/client_agent.py`, `src/simulator/runner.py`, `src/yaml_config/constants.yaml`, `tests/test_bug4_objection_metrics.py` (216 строк), `tests/test_sources_objection.py`

**Описание:** Исправлена цепочка метрик возражений (BUG #4): `IntentTracker` теперь корректно считает последовательные возражения, `objection_guard` получает правильный счётчик, `objection_return` активируется при превышении лимита. Симулятор обновлён для генерации сценариев с повторными возражениями.

---

## [3be5ed5] Fix autonomous anti-loop chain (Bug #12b) with targeted tests

**Затронутые файлы:** `src/blackboard/sources/autonomous_decision.py`, `src/blackboard/sources/fact_question.py`, `src/conditions/policy/conditions.py`, `src/conditions/policy/context.py`, `src/context_envelope.py`, `src/context_window.py`, `src/dialogue_policy.py`, `src/generator.py`, `src/settings.py/.yaml`, `src/yaml_config/__init__.py`, `src/yaml_config/constants.py/.yaml`, `tests/test_bug12b_antiloop_chain.py` (379 строк)

**Описание:** Баг #12b — цикл внутри автономного режима при переходе discovery→qualification. `ContextWindow` получил детектор повторных state-переходов. `AutonomousDecisionSource` блокирует переход обратно в discovery если уже выполнен. `fact_question.py` перестаёт задавать одинаковые вопросы.

---

## [446d0dc] Fix simulator lead scoring enablement and temperature aggregation

**Затронутые файлы:** `src/feature_flags.py`, `src/settings.yaml`, `src/simulator/metrics.py`, `src/simulator/report.py`, `src/simulator/runner.py`, тесты

**Описание:** Lead scoring в симуляторе не включался из-за флага в `feature_flags`. Агрегация temperature по репликам была некорректной (деление на 0 для пустых диалогов). `SimulatorReport` дополнен полем lead_score. 156-строчные тесты.

---

## [e55b30c] fix(autonomous): break discovery oscillation loop (bug #12)

**Затронутые файлы:** `src/blackboard/priority_assigner.py`, `src/blackboard/sources/autonomous_decision.py`, `src/config_loader.py`, `src/context_envelope.py`, `tests/test_bug12_oscillation_fix.py` (967 строк)

**Описание:** Баг #12 — осцилляция в состоянии discovery: бот зацикливался задавая одни и те же вопросы о бизнесе. `ContextEnvelope` получил счётчик turns-in-state. `AutonomousDecisionSource` форсирует переход в qualification при `turns_in_discovery >= threshold`. `config_loader` загружает новые параметры. 967-строчные тесты.

---

## [60a1d59] fix: prevent premature soft_close and credential leaks (bugs #7, #8)

**Затронутые файлы:** `src/blackboard/sources/autonomous_decision.py`, `src/blackboard/sources/transition_resolver.py`, `src/bot.py`, `src/config.py`, `src/config_loader.py`, `src/generator.py`, `src/knowledge/autonomous_kb.py`, `src/knowledge/base.py`, `src/knowledge/data/pricing.yaml`, `src/knowledge/data/products.yaml`, `src/knowledge/data/support.yaml`, `src/knowledge/loader.py`, `src/knowledge/retriever.py`, `src/objection_handler.py`, `src/yaml_config/flows/autonomous/states.yaml`, `tests/test_bug_fixes_7_8.py` (956 строк)

**Описание:** Баг #7 — преждевременный `soft_close` до завершения presentation. Баг #8 — утечка credentials в retriever (URL/пароли из KB передавались в промпт). `TransitionResolver` теперь проверяет фазу диалога перед soft_close. Retriever фильтрует чувствительные поля. 956-строчные тесты.

---

## [08308c6] fix: suppress inappropriate apologies and greeting fallback (bugs #5, #6)

**Затронутые файлы:** `src/apology_ssot.py`, `src/generator.py`, `src/response_directives.py`, `src/tone_analyzer/regex_analyzer.py`, `src/yaml_config/constants.py/.yaml`, `src/yaml_config/flows/_base/states.yaml`, тесты (450 строк суммарно)

**Описание:** Баг #5 — бот вставлял приветствие ("Здравствуйте!") в середине диалога при смене состояния. Баг #6 — неуместные извинения на любое возражение. `apology_ssot.py` расширен intent-aware логикой (no apology при rejection/price_question). `ResponseDirectives` блокирует greeting после turn>0.

---

## [deb0485] feat: enhance indexer, personas, simulation and autonomous flow

**Затронутые файлы:** `.gitignore`, `codebase_analyzer/` (graph + indexer), `docs/INTEGRATION_SPEC.md`, `docs/INTENT_TAXONOMY.md`, `scripts/run_full_simulation_100.py`, `src/blackboard/sources/autonomous_decision.py`, `src/simulator/personas.py`, `src/yaml_config/flows/autonomous/states.yaml`

**Описание:** Комплексное улучшение: `codebase_analyzer` получил dependency graph и расширенный индексатор. Добавлены 5 новых персон в симулятор (204 строки). `run_full_simulation_100.py` рефакторинг с улучшенным параллелизмом. `autonomous_decision.py` получил дополнительные guard-условия для переходов.

---

## [5a4f894] fix(autonomous): break deterministic looping with 5 structural fixes

**Затронутые файлы:** `src/blackboard/sources/autonomous_decision.py`, `src/blackboard/sources/phase_exhausted.py`, `src/bot.py`, `src/config_loader.py`, `src/context_window.py`, `src/generator.py`, `src/knowledge/autonomous_kb.py`, `src/yaml_config/flows/autonomous/states.yaml`

**Описание:** Пять структурных исправлений детерминированного зацикливания: (1) `phase_exhausted` триггерит при N повторных intent без прогресса, (2) `ContextWindow` считает уникальные topics covered, (3) `config_loader` правильно загружает autonomous-параметры, (4) `autonomous_kb` не возвращает одни и те же факты дважды, (5) генератор рандомизирует порядок вопросов.

---

## [8bef3b7] fix(api): enforce structured auth/profile errors

**Затронутые файлы:** `docs/DEPLOYMENT.md`, `src/api.py`, `tests/test_api_error_contract.py` (29 строк)

**Описание:** API теперь возвращает структурированные JSON-ошибки для auth-failures и profile-not-found вместо HTTP 500. Контракт ошибок задокументирован в DEPLOYMENT.md и покрыт тестами.

---

## [f52f874] fix(api): harden autonomous prod contract and deployment guide

**Затронутые файлы:** `docs/DEPLOYMENT.md` (переработан), `src/api.py` (+86 строк), `tests/test_api_error_contract.py` (+72 строки)

**Описание:** Ужесточение контракта production API: валидация входящих параметров, строгие типы ответов, обработка таймаутов Ollama. DEPLOYMENT.md переработан (316→226 строк — сокращение за счёт убранных устаревших разделов, +дополнительные инструкции по деплою).

---

## [f9a33ab] fix(api): enable_tracing propagation in from_snapshot + SQLite WAL mode

**Затронутые файлы:** `src/api.py`, `src/bot.py`, `tests/test_api_fixes.py` (221 строка)

**Описание:** `Bot.from_snapshot()` не передавал флаг `enable_tracing` — трейсинг отключался при восстановлении из snapshot. SQLite переведён в WAL-режим для concurrent reads. 221-строчные тесты проверяют оба исправления.

---

## [2589082] fix(autonomous): rename decision_timeline → timeline in states.yaml

**Затронутые файлы:** `src/yaml_config/flows/autonomous/states.yaml`

**Описание:** Переименование поля `decision_timeline` в `timeline` в конфиге состояний autonomous-флоу. Приводит конфиг в соответствие с именованием в коде.

---

## [62a55da] feat(autonomous): production API + comprehensive user data collection

**Затронутые файлы:** `pyproject.toml`, `src/api.py` (343 строки, новый), `src/blackboard/sources/autonomous_decision.py`, `src/context_window.py`, `src/settings.yaml`, `src/yaml_config/constants.yaml`, `src/yaml_config/flows/autonomous/states.yaml`

**Описание:** Создан production REST API (`src/api.py`) с FastAPI. Комплексный сбор данных пользователя: `context_window.py` хранит все извлечённые поля по ходу диалога. `autonomous_decision.py` интегрирован с data collection pipeline. `constants.yaml` расширен полями для всех собираемых данных.

---

## [5431bc0] fix(autonomous): deterministic LLM-driven objection handling

**Затронутые файлы:** `src/blackboard/sources/autonomous_decision.py`, `src/generator.py`, `src/yaml_config/templates/autonomous/prompts.yaml`, `tests/test_sources_autonomous_decision.py` (540 строк)

**Описание:** Обработка возражений переведена с rule-based на LLM-driven с детерминированными guard-условиями. `AutonomousDecisionSource` определяет тип возражения (price/feature/trust/timing) и маршрутизирует в соответствующий промпт-шаблон. Генератор получает explicit objection_type в контексте. 540-строчные тесты.

---

## [e2b40ce] docs(deploy): align with MVP integration spec (n8n → Redis → AI)

**Затронутые файлы:** `docs/DEPLOYMENT.md`

**Описание:** Полный апдейт DEPLOYMENT.md под MVP-архитектуру: n8n как оркестратор вебхуков, Redis для session storage, Ollama как AI backend. Документация описывает реальный стек интеграции.

---

## [08710cd] docs: add deployment guide

**Затронутые файлы:** `docs/DEPLOYMENT.md` (764 строки, новый)

**Описание:** Создан полный гайд по деплою: требования, установка зависимостей, конфигурация Ollama, запуск API, мониторинг, troubleshooting.

---

## [76b42e4] Add realistic contract-alignment integration tests

**Затронутые файлы:** `tests/test_contract_alignment_realistic.py` (464 строки, новый)

**Описание:** Интеграционные тесты на соответствие API-контракту с реалистичными сценариями диалогов. Проверяют: формат ответа, обязательные поля, коды ошибок, поведение при timeout Ollama.

---

## [f696e4c] Align contracts and add response boundary guardrail

**Затронутые файлы:** `src/bot.py` (+248 строк), `src/classifier/extractors/extraction_validator.py`, `src/classifier/unified.py`, `src/decision_trace.py`, `src/feature_flags.py`, `src/generator.py` (+232 строки), `src/response_boundary_validator.py` (249 строк, новый), `src/response_diversity.py`, `src/simulator/report.py/.runner.py`, тесты (17 файлов)

**Описание:** Создан `ResponseBoundaryValidator` — слой валидации ответов бота: блокирует ответы без KB-обоснования, урезает слишком длинные ответы, детектирует repetition. `bot.py` и `generator.py` существенно расширены для поддержки нового контракта. Масштабный коммит (1004 добавленных строки).

---

## [aabed11] fix(policy): harden objection overlay gating and CTA blocking

**Затронутые файлы:** `src/conditions/policy/__init__.py`, `src/conditions/policy/conditions.py`, `src/conditions/policy/context.py`, `src/context_envelope.py`, `src/cta_generator.py`, `src/dialogue_policy.py`, `src/yaml_config/constants.yaml`, тесты (568 строк суммарно, 16 файлов)

**Описание:** Ужесточение гейтинга overlay для возражений: CTA (call-to-action) блокируется в состояниях objection_handling и negotiation. `PolicyContext` расширен полями для отслеживания active overlays. `ContextEnvelope` получил 102 строки новых методов для управления состоянием диалога. Покрытие тестами 8 новых тест-файлов.

---

## [37ee23a] Fix excessive disambiguation chain (4 root causes)

**Затронутые файлы:** `src/classifier/confidence_calibration.py`, `src/classifier/disambiguation_engine.py`, `src/classifier/refinement_layers.py`, `src/classifier/refinement_pipeline.py`, `src/yaml_config/constants.py/.yaml`, `tests/test_disambiguation_engine.py`, `tests/test_refinement_pipeline.py` (249 строк, новый)

**Описание:** Четыре корневые причины избыточного disambiguation: (1) слишком низкий порог confidence для тригера, (2) отсутствие max_disambiguation_turns, (3) refinement_layers пропускали очевидные интенты на переклассификацию, (4) calibration сдвигал уверенность вниз для длинных сообщений. Все исправлены.

---

## [5ec919f] Fix factual hallucination chain: ground Q&A templates on real KB data

**Затронутые файлы:** `src/config.py`, `src/generator.py`, `src/knowledge/retriever.py`, `src/yaml_config/templates/_base/prompts.yaml`, шаблон spin_selling, тесты (916 добавленных строк, 11 файлов)

**Описание:** Цепочка галлюцинаций: Q&A-шаблоны содержали placeholder-цены и фичи → LLM принимал их за факты → генерировал выдуманные данные. Retriever обязан возвращать реальные KB-данные перед рендером Q&A-шаблона. Промпт-шаблоны переписаны под `{retrieved_facts}` без hardcoded значений.

---

## [903a1a2] Replace prose_style_engine with narrative_style rules

**Затронутые файлы:** `*.compressed` (compressed prompt file)

**Описание:** В сжатом промпт-файле заменён модуль `prose_style_engine` на более компактные `narrative_style` правила. Уменьшение токен-нагрузки при сохранении функциональности управления стилем ответов.

---

## [f17ed2e] Refine prose style controls in compressed prompt

**Затронутые файлы:** `*.compressed`

**Описание:** Уточнение управляющих директив стиля прозы в сжатом промпте: добавлены правила для length control, formality level, bullet vs prose formatting.

---

## [5caee26] Refine lore pack and tighten strict provenance/voiceprint rules

**Затронутые файлы:** `*.compressed`

**Описание:** Обновлён lore-пакет (контекст о продукте/компании). Ужесточены правила строгого провенанса (все факты только из KB) и voiceprint (консистентный голос бота). +224 строки в compressed prompt.

---

## [9e86e28] Refactor COGITATOR prompt to v7 architecture

**Затронутые файлы:** `*.compressed`

**Описание:** Рефактор сжатого мастер-промпта до архитектуры v7: переструктурированы модули, убраны дублирующиеся секции (−922 строки), добавлены новые (+436 строк). Уменьшение токен-нагрузки при улучшении структурности инструкций.

---

## [55f197e] Upgrade COGITATOR engine to v6.1 lean-arc

**Затронутые файлы:** `*.compressed`

**Описание:** Промежуточное обновление COGITATOR до v6.1 "lean architecture": убраны тяжёлые модули tau и sororitas, оставлен минимально необходимый core. +91 строка эффективных инструкций.

---

## [f673864] refactor prompt to v6.1 and remove tau/sororitas modules

**Затронутые файлы:** `*.compressed`

**Описание:** Первичный рефактор compressed prompt — создание v6.1 базы: 959 строк новых правил, удалены устаревшие roleplay-модули (tau/sororitas).

---

## [be28e4c] Harden state transitions and logging contracts

**Затронутые файлы:** `.github/workflows/contracts.yml` (новый), `scripts/run_contract_guards.sh`, `src/blackboard/blackboard.py`, `src/blackboard/conflict_resolver.py`, `src/blackboard/decision_sanitizer.py` (104 строки, новый), `src/blackboard/orchestrator.py`, `src/bot.py`, `src/rules/intent_taxonomy.py`, `src/rules/resolver.py`, `src/simulator/metrics.py`, `src/tone_analyzer/` (2 файла), тесты (990 добавленных строк, 20 файлов)

**Описание:** Крупный инфраструктурный коммит. `DecisionSanitizer` — новый слой валидации решений blackboard перед применением. CI workflow для проверки контрактов. Оркестратор hardened: строгая последовательность применения KnowledgeSource результатов. Стандартизированы logging-контракты (уровни, форматы).

---

## [fa4451d] docs: align README/API/INTEGRATION_SPEC with runtime contracts

**Затронутые файлы:** `README.md`, `docs/API.md`, `docs/INTEGRATION_SPEC.md`, `docs/txt/INTEGRATION_SPEC.txt`

**Описание:** Синхронизация документации с реальным поведением runtime: обновлены примеры API-запросов/ответов, контракты снепшотов, описание трейсинга.

---

## [759d3f8] Stabilize blackboard/config runtime and unify src namespace imports

**Затронутые файлы:** `README.md`, `conftest.py`, `docs/API.md`, 30+ скриптов в `scripts/`, `src/__init__.py`, `src/blackboard/orchestrator.py`, `src/blackboard/source_registry.py`, `src/bot.py`, `src/config_loader.py`, `src/feature_flags.py`, `src/import_aliases.py` (127 строк, новый), `src/settings.py`, удалены `tests/codebase_analyzer/` (15 тест-файлов)

**Описание:** Унификация импортов через `src/__init__.py` и `src/import_aliases.py`. `source_registry.py` рефакторинг (542 строки). Все скрипты переведены на единый namespace `from src.X import Y`. Удалены устаревшие тесты codebase_analyzer.

---

## [3536773] docs: update INTEGRATION_SPEC versions to match upgraded deps

**Затронутые файлы:** `docs/INTEGRATION_SPEC.md`, `docs/txt/INTEGRATION_SPEC.txt`

**Описание:** Актуализация версий зависимостей в INTEGRATION_SPEC после обновления pyproject.toml.

---

## [dfc4066] chore: upgrade Python >=3.12 and bump all deps to current stable

**Затронутые файлы:** `knowledge_extractor/pyproject.toml`, `pyproject.toml`, `requirements.txt`, `seo_rewriter/pyproject.toml`, `voice_bot/requirements.txt`

**Описание:** Апгрейд минимальной версии Python с 3.10 до 3.12. Обновление всех зависимостей до актуальных стабильных версий в 5 pyproject/requirements файлах.

---

## [376e967] docs: apply reviewer feedback — mandatory trace, remove SessionManager, reframe config

**Затронутые файлы:** `docs/INTEGRATION_SPEC.md`, `docs/txt/INTEGRATION_SPEC.txt`

**Описание:** Правки по review: трейсинг стал обязательным полем в API-ответе, убран несуществующий `SessionManager` из документации, переформулирован раздел конфигурации.

---

## [852a3a9] docs: fix 6 inaccuracies in INTEGRATION_SPEC verified against codebase

**Затронутые файлы:** `docs/INTEGRATION_SPEC.md`, `docs/txt/INTEGRATION_SPEC.txt`

**Описание:** Исправление 6 фактических неточностей в INTEGRATION_SPEC выявленных при верификации против кода: имена методов, форматы параметров, поведение edge-cases.

---

## [d876b27] docs: fix metrics and fallback snapshots to match actual code

**Затронутые файлы:** `docs/INTEGRATION_SPEC.md`, `docs/txt/INTEGRATION_SPEC.txt`

**Описание:** Исправление документации метрик и fallback-снепшотов: реальные имена полей, правильные дефолтные значения, корректное поведение при деградации.

---

## [9cd633e] feat: runtime config override (hot-reload) without redeploy

**Затронутые файлы:** `docs/INTEGRATION_SPEC.md`, `docs/txt/INTEGRATION_SPEC.txt`, `src/bot.py`, `src/config_loader.py`, `src/response_directives.py`, `tests/test_config_override.py` (1235 строк)

**Описание:** Hot-reload конфигурации без перезапуска: `config_loader.py` (+117 строк) реализует watcher на изменения YAML-файлов, `bot.py` применяет новый конфиг на следующем turn. Покрытие тестами 1235 строк.

---

## [0298a6f] docs: fix 8 inaccuracies in INTEGRATION_SPEC verified against codebase

**Затронутые файлы:** `docs/INTEGRATION_SPEC.md`, `docs/txt/INTEGRATION_SPEC.txt`

**Описание:** Исправление 8 неточностей в INTEGRATION_SPEC: расхождения в именах endpoint, форматах snapshot, поведении таймаутов.

---

## [5e92d7f] docs: align INTEGRATION_SPEC with actual codebase

**Затронутые файлы:** `docs/INTEGRATION_SPEC.md`, `docs/txt/INTEGRATION_SPEC.txt`

**Описание:** Масштабная переработка INTEGRATION_SPEC (1669→новая структура). Приведение всего документа в соответствие с реальным поведением кода. Добавлены секции по autonomous flow, blackboard API, classifier pipeline.

---

## [e01c98c] fix: complete encapsulation & abstraction repair (Issues #4-#7)

**Затронутые файлы:** `src/blackboard/blackboard.py`, `src/blackboard/models.py`, `src/blackboard/orchestrator.py`, `src/blackboard/protocols.py`, `src/blackboard/sources/go_back_guard.py`, `src/blackboard/sources/objection_return.py`, `src/blackboard/sources/stall_guard.py`, `src/intent_tracker.py`, `src/state_machine.py`, тесты (1340 добавленных строк, 28 файлов)

**Описание:** Глобальный ремонт инкапсуляции blackboard-системы (issues #4-#7): Blackboard не раскрывает внутренние структуры через публичный API, Models стали immutable dataclasses, Protocols задают четкие интерфейсы KnowledgeSource. `state_machine.py` рефакторинг. 28 тест-файлов обновлены.

---

## [9c3c216] fix: enforce mutation ownership — Orchestrator is single owner of state mutation

**Затронутые файлы:** `src/blackboard/blackboard.py`, `src/blackboard/conflict_resolver.py`, `src/blackboard/enums.py`, `src/blackboard/models.py`, `src/blackboard/sources/data_collector.py`, `src/state_machine.py`, тесты (11 файлов)

**Описание:** Принципиальное архитектурное исправление: только `Orchestrator` имеет право мутировать state blackboard. `ConflictResolver` лишён прямого write-доступа. `data_collector` работает через proposals, не прямые записи. Удалены тесты проверявшие неправильное поведение.

---

## [955f64c] fix: action validation SSOT + snapshot serialization contract — two structural bugs

**Затронутые файлы:** `src/blackboard/orchestrator.py`, `src/bot.py`, `src/generator.py`, `src/state_machine.py`, `tests/test_blackboard_proposal_validator.py` (79 строк), `tests/test_snapshot.py` (140 строк)

**Описание:** Два структурных бага: (1) валидация action выполнялась в нескольких местах — создан единственный SSOT-валидатор в orchestrator. (2) Сериализация snapshot не сохраняла часть полей state_machine — исправлен контракт (де)сериализации.

---

## [11ae6d8] fix: broken config pipeline + turn counter coupling — two critical safety bugs

**Затронутые файлы:** `src/blackboard/` (4 файла), `src/bot.py`, `src/config_loader.py`, `src/intent_tracker.py`, `src/state_machine.py`, `src/yaml_config/constants.yaml`, тесты (29 файлов +215 строк)

**Описание:** Два критических бага безопасности: (1) config pipeline не применял overrides к вложенным структурам — бот игнорировал часть конфигурации. (2) turn counter в state_machine был связан с intent_tracker — при reset одного сбрасывался другой. Оба исправлены с изоляцией счётчиков.

---

## [9b7bfee] fix: eliminate dead intents, broken mixin loading, ghost intents + add systemic CI guards

**Затронутые файлы:** `src/blackboard/sources/escalation.py`, `src/classifier/llm/prompts.py`, `src/classifier/llm/schemas.py`, `src/config.py`, `src/config_loader.py`, `src/validation/intent_coverage.py` (28 строк, новый), `src/yaml_config/constants.py/.yaml`, `src/yaml_config/flows/_base/mixins.yaml`, тесты (14 файлов)

**Описание:** Три категории дефектов: (1) "мёртвые" интенты в constants.yaml которые нигде не обрабатывались. (2) Mixin-файлы не загружались из-за неправильного пути в `config_loader`. (3) "Призрак-интенты" — LLM иногда возвращал интенты не из таксономии, classifier их пропускал. Добавлен CI guard `intent_coverage.py`.

---

## [f811196] fix: three critical bugs — config/flow sync, composite conditions, repair cascade

**Затронутые файлы:** `src/blackboard/orchestrator.py`, `src/blackboard/sources/intent_processor.py`, `src/blackboard/sources/transition_resolver.py`, `src/bot.py`, `src/conditions/expression_parser.py`, `src/conditions/policy/` (3 файла), `src/config_loader.py`, `src/context_envelope.py`, `src/dialogue_policy.py`, `src/rules/resolver.py`, `src/state_machine.py`, тесты (`test_three_critical_bugs.py` — 728 строк)

**Описание:** Три критических бага: (1) config/flow десинхронизация при reload — состояния флоу не обновлялись. (2) Composite conditions (`AND`/`OR`) в expression_parser не вычислялись корректно при вложенности. (3) Repair cascade — при ошибке blackboard следующие KnowledgeSources продолжали работу с некорректным state.

---

## [0016d81] fix: persona-aware objection limits + taxonomy fallback in Blackboard

**Затронутые файлы:** `src/blackboard/blackboard.py`, `src/blackboard/sources/intent_processor.py`, `src/blackboard/sources/objection_guard.py`, `src/blackboard/sources/transition_resolver.py`, `src/conditions/state_machine/context.py`, `src/rules/resolver.py`, `src/state_machine.py`, `src/yaml_config/constants.py/.yaml`, тесты (13 файлов)

**Описание:** Лимиты возражений теперь зависят от персоны клиента (aggressive persona — больший лимит, tire_kicker — меньший). `intent_processor` получил taxonomy fallback: если LLM вернул unknown intent → маппинг на ближайший known. `resolver.py` добавлена защита от пустой таксономии.

---

*Документ сгенерирован: 2026-02-19. Коммиты: 69, от `0016d81` до `49a1e4a`.*
