# A/B v2: factual verifier OFF vs ON на тех же 21 диалогах

- Источник клиентских реплик: results/manual_e2e_dialogs_full_transcript.md
- Диалогов: 21
- Реплик (OFF): 104
- Реплик (ON): 104

## Метрики нарушений (deterministic audit)
- All violations: 4 -> 3
- Hard violations: 1 -> 2
- Turns with violations: 4 -> 3
- Factual turns with violations: 1/60 -> 2/60
- 'Уточню у коллег' count: 4 -> 48

## Verifier usage (ON)
- used: 52
- changed: 3
- verdict pass: 5
- verdict fail: 47
- verdict error: 0
- verdict not_run: 52

## Top violation types OFF
- unrequested_business_assumption: 2
- mid_conversation_greeting: 1
- hallucinated_past_action: 1

## Top violation types ON
- hallucinated_past_action: 2
- unrequested_business_assumption: 1
