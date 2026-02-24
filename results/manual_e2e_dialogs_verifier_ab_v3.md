# A/B v3: factual verifier OFF vs ON на тех же 21 диалогах

- Источник клиентских реплик: results/manual_e2e_dialogs_full_transcript.md
- Диалогов: 21
- Реплик (OFF): 104
- Реплик (ON): 104

## Метрики нарушений (deterministic audit)
- All violations: 4 -> 3
- Hard violations: 1 -> 1
- Turns with violations: 4 -> 3
- Factual turns with violations: 2/60 -> 1/60
- 'Уточню у коллег' count: 3 -> 22

## Verifier usage (ON)
- used: 53
- changed: 4
- verdict pass: 5
- verdict fail: 48
- verdict error: 0
- verdict not_run: 51

## Top violation types OFF
- unrequested_business_assumption: 3
- hallucinated_past_action: 1

## Top violation types ON
- unrequested_business_assumption: 1
- hallucinated_past_action: 1
- mid_conversation_greeting: 1
