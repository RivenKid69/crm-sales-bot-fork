# A/B v4: factual verifier OFF vs ON на тех же 15 диалогах

- Источник клиентских реплик: results/manual_e2e_dialogs_full_transcript.md
- Диалогов: 15
- Реплик (OFF): 74
- Реплик (ON): 74

## Метрики нарушений (deterministic audit)
- All violations: 4 -> 4
- Hard violations: 2 -> 3
- Turns with violations: 3 -> 3
- Factual turns with violations: 3/39 -> 3/38
- 'Уточню у коллег' count: 0 -> 0

## Verifier usage (ON)
- used: 40
- changed: 40
- verdict pass: 1
- verdict fail: 39
- verdict error: 0
- verdict not_run: 34

## Top violation types OFF
- hallucinated_past_action: 2
- ungrounded_stats: 1
- ungrounded_guarantee: 1

## Top violation types ON
- hallucinated_past_action: 3
- ungrounded_stats: 1
