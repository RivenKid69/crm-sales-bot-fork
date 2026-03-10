# PAIN REALISTIC E2E: 2026-03-05 vs 2026-03-10

Сравниваем:

- `results/pain_realistic_e2e_10_20260305_113946.json`
- `results/pain_realistic_e2e_10_20260310_100703.json`

## Общий итог

- `2026-03-05`: `4/10 PASS`
- `2026-03-10`: `4/10 PASS`

Итоговый счёт не изменился, но часть успешных сценариев стала заметно точнее по pain-topic.

## По диалогам

| ID | Было | Стало | Кратко |
|---|---:|---:|---|
| D01 | PASS | PASS | Улучшилось: вместо `equipment_slow_boot_1708` теперь точный `kassa_freeze_peak_hours_601` |
| D02 | PASS | PASS | Сильно улучшилось: вместо `ops_speed_slow_checkout_001` теперь точный `equipment_scanner_not_first_try_1703`, исчезли issues |
| D03 | FAIL | FAIL | Без изменений |
| D04 | PASS | PASS | Всё ещё PASS, но topic по-прежнему не целевой |
| D05 | PASS | PASS | Без изменений, topic всё ещё не целевой |
| D06 | FAIL | FAIL | Без изменений по verdict |
| D07 | FAIL | FAIL | Без изменений по verdict |
| D08 | FAIL | FAIL | Без изменений по verdict |
| D09 | FAIL | FAIL | Без изменений по verdict |
| D10 | FAIL | FAIL | Без изменений по verdict |

## Что реально стало лучше

### D01

- Было:
  - `topic=equipment_slow_boot_1708`
  - issue: `topic=equipment_slow_boot_1708 (ожидался kassa_freeze_peak_hours_601)`
- Стало:
  - `topic=kassa_freeze_peak_hours_601`
  - issues: нет

### D02

- Было:
  - `topic=ops_speed_slow_checkout_001`
  - issue: `боль НЕ в ответе бота`
- Стало:
  - `topic=equipment_scanner_not_first_try_1703`
  - issues: нет

## Что не изменилось по счёту

- `D03`, `D06`, `D07`, `D08`, `D09`, `D10` остались `FAIL`
- `D04`, `D05` остались `PASS`, но всё ещё с промахом по целевому topic

## Важное наблюдение по structured output

Во время полного прогона `2026-03-10` исправленный кейс с невалидными `alternatives[*].intent` больше не валил часть диалогов: такие альтернативы теперь отбрасываются, а не ломают весь classifier call.

Но полный 10-dialog run показал ещё оставшиеся отдельные structured-output проблемы вне этого фиксa:

- top-level `ClassificationResult.intent` иногда приходит вне schema
- `extracted_data.pain_category` иногда приходит вне schema
- местами всплывает `AutonomousDecision` schema mismatch

То есть сделанный фикс улучшил один реальный класс сбоев и улучшил качество `D01/D02`, но не закрыл все structured-output риски во всём autonomous pipeline.
