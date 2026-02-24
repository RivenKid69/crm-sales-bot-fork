# Phases

Документ фиксирует фактические фазы развития, отражённые в коде и feature flags.

## Фаза 0. Инфраструктура

- `src/logger.py`
- `src/metrics.py`
- `src/feature_flags.py`

Флаги: `structured_logging`, `metrics_tracking`.

## Фаза 1. Надёжность и защита

- `src/conversation_guard.py`
- `src/fallback_handler.py`

Флаги: `conversation_guard`, `multi_tier_fallback`, `conversation_guard_in_pipeline`.

## Фаза 2. Естественность диалога

- `src/tone_analyzer/*`
- `src/response_variations.py`
- `src/response_diversity.py`
- `src/question_dedup.py`

Флаги: `tone_analysis`, `response_variations`, `response_diversity`, `question_deduplication`, `apology_system`.

## Фаза 3. Продажи и conversion logic

- `src/lead_scoring.py`
- `src/objection_handler.py`
- `src/cta_generator.py`
- `src/dialogue_policy.py`

Флаги: `lead_scoring`, `objection_handler`, `cta_generator`, `context_policy_overlays`.

## Фаза 4. Классификация и disambiguation

- `src/classifier/unified.py`
- `src/classifier/refinement_pipeline.py`
- `src/classifier/disambiguation_engine.py`

Флаги: `llm_classifier`, `refinement_pipeline`, `unified_disambiguation` и связанные refinement-флаги.

## Фаза 5. Blackboard orchestration

- `src/blackboard/orchestrator.py`
- `src/blackboard/sources/*.py`

Фактически это основной runtime-маршрут принятия решения в `SalesBot.process()`.

## Фаза 6. Контекст и трассировка

- `src/context_envelope.py`
- `src/context_window.py`
- `src/decision_trace.py`

Флаги: `context_full_envelope`, `context_response_directives`, `context_policy_overlays`.

## Что считать актуальным

Если поведение описано в документации, но не подтверждается кодом в `src/`, приоритет у кода.
