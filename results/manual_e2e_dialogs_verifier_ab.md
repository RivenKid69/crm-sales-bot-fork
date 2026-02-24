# A/B: factual verifier OFF vs ON на тех же 20 диалогах

- Источник клиентских реплик: results/manual_e2e_dialogs_full_transcript.md
- Диалогов: 21
- Реплик (OFF): 104
- Реплик (ON): 104

## Метрики нарушений (deterministic audit)
- All violations: 1 -> 9
- Hard violations: 1 -> 6
- Turns with violations: 1 -> 9
- Factual turns with violations: 1/60 -> 7/60
- 'Уточню у коллег' count: 3 -> 1

## Verifier usage (ON)
- used: 53
- changed: 2
- verdict pass: 4
- verdict fail: 49
- verdict error: 0
- verdict not_run: 51

## Top violation types OFF
- hallucinated_past_action: 1

## Top violation types ON
- hallucinated_past_action: 6
- unrequested_business_assumption: 3
