# Сравнение качества: те же 20 диалогов (до/после factual verifier)

- Диалогов: 20
- Реплик бота до: 65
- Реплик бота после: 97

## Метрики нарушений (ResponseBoundary deterministic audit)
- All violations: 2 -> 8
- Hard violations: 1 -> 6
- Turns with violations: 2 -> 8
- Factual turns with violations: 1/26 -> 7/55

## Использование factual verifier (после)
- Used turns: 52
- Changed turns: 0
- Verdict pass: 4
- Verdict fail: 47
- Verdict not_run: 45

## Top violation types (до)
- hallucinated_past_action: 1
- unrequested_business_assumption: 1

## Top violation types (после)
- hallucinated_past_action: 6
- mid_conversation_greeting: 1
- unrequested_business_assumption: 1
