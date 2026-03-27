# Последние 10 Live API прогонов

Зафиксировано: `2026-03-26 14:35` (`Asia/Almaty`)

Источник:
- top-level каталоги в `results/live_api_real_payload`
- сортировка по filesystem `mtime` каталога

Примечания:
- `status = complete` означает, что на top-level есть `transcript.md`, либо это batch-каталог с дочерними сценариями и `transcript.md` внутри них
- `status = partial_or_unclear` означает, что top-level `transcript.md` нет, поэтому по одному имени каталога нельзя считать прогон гарантированно завершённым

## Реестр

| Date | Time | Run | Type | Status | Details |
|---|---|---|---|---|---|
| 2026-03-26 | 14:23:01 | `batch_20260326_history_recheck` | `batch` | `complete` | 3 scenario dirs, 3 with `transcript.md` |
| 2026-03-26 | 14:08:52 | `20260326_090515` | `single` | `complete` | top-level `transcript.md` present |
| 2026-03-26 | 11:35:23 | `smoke_20260326_R03` | `single` | `partial_or_unclear` | no top-level `transcript.md` |
| 2026-03-26 | 11:34:32 | `smoke_20260326_R06` | `single` | `complete` | top-level `transcript.md` present |
| 2026-03-26 | 10:09:13 | `batch_20260326_091111_rerun` | `batch` | `complete` | 10 scenario dirs, 10 with `transcript.md` |
| 2026-03-24 | 20:56:41 | `batch_20260324_1948` | `batch` | `complete` | 10 scenario dirs, 10 with `transcript.md` |
| 2026-03-24 | 19:27:55 | `scenario2_fixcheck` | `single` | `complete` | top-level `transcript.md` present |
| 2026-03-24 | 19:25:48 | `scenario1_fixcheck` | `single` | `complete` | top-level `transcript.md` present |
| 2026-03-24 | 16:19:05 | `20260324_111504` | `single` | `complete` | top-level `transcript.md` present |
| 2026-03-24 | 15:07:40 | `20260324_100040` | `single` | `partial_or_unclear` | no top-level `transcript.md` |

## Пути

- [batch_20260326_history_recheck](/home/corta/crm-sales-bot-fork/results/live_api_real_payload/batch_20260326_history_recheck)
- [20260326_090515](/home/corta/crm-sales-bot-fork/results/live_api_real_payload/20260326_090515)
- [smoke_20260326_R03](/home/corta/crm-sales-bot-fork/results/live_api_real_payload/smoke_20260326_R03)
- [smoke_20260326_R06](/home/corta/crm-sales-bot-fork/results/live_api_real_payload/smoke_20260326_R06)
- [batch_20260326_091111_rerun](/home/corta/crm-sales-bot-fork/results/live_api_real_payload/batch_20260326_091111_rerun)
- [batch_20260324_1948](/home/corta/crm-sales-bot-fork/results/live_api_real_payload/batch_20260324_1948)
- [scenario2_fixcheck](/home/corta/crm-sales-bot-fork/results/live_api_real_payload/scenario2_fixcheck)
- [scenario1_fixcheck](/home/corta/crm-sales-bot-fork/results/live_api_real_payload/scenario1_fixcheck)
- [20260324_111504](/home/corta/crm-sales-bot-fork/results/live_api_real_payload/20260324_111504)
- [20260324_100040](/home/corta/crm-sales-bot-fork/results/live_api_real_payload/20260324_100040)
