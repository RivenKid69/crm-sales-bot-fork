# Real-Client-Based Live API Scenarios

Ниже лежат 11 E2E-сценариев в формате, который уже поддерживает корневой `live_api_real_payload_e2e.py` через `--events-file`.

Все сценарии собраны строго из повторяющихся паттернов в `диалоги/TXT.txt` и JPG-скриншотах в `диалоги/`. Новых продуктовых обещаний не добавлено: только реальные темы, формулировки и конфликтные места из живых диалогов.

Готовые команды запуска позже:

```bash
python3 -u live_api_real_payload_e2e.py --events-file scripts/live_api_real_payload_scenarios/R01_invoice_kit_bonus_trial.json
python3 -u live_api_real_payload_e2e.py --events-file scripts/live_api_real_payload_scenarios/R02_installment_umag_training_migration.json
python3 -u live_api_real_payload_e2e.py --events-file scripts/live_api_real_payload_scenarios/R03_prepayment_trust_city_reference_followup.json
python3 -u live_api_real_payload_e2e.py --events-file scripts/live_api_real_payload_scenarios/R04_mixed_kz_ru_equipment_pushback.json
python3 -u live_api_real_payload_e2e.py --events-file scripts/live_api_real_payload_scenarios/R05_whatsapp_unknown_integration_plain_words.json
python3 -u live_api_real_payload_e2e.py --events-file scripts/live_api_real_payload_scenarios/R06_one_employee_phone_only_trial.json
python3 -u live_api_real_payload_e2e.py --events-file scripts/live_api_real_payload_scenarios/R07_clothing_store_onboarding_pains.json
python3 -u live_api_real_payload_e2e.py --events-file scripts/live_api_real_payload_scenarios/R08_non_grocery_bundle_fit_installments.json
python3 -u live_api_real_payload_e2e.py --events-file scripts/live_api_real_payload_scenarios/R09_chaotic_buyer_invoice_to_trial.json
python3 -u live_api_real_payload_e2e.py --events-file scripts/live_api_real_payload_scenarios/R10_cross_day_memory_voice_note_trial_start.json
python3 -u live_api_real_payload_e2e.py --events-file scripts/live_api_real_payload_scenarios/R11_second_screen_followup_hallucination_trace.json
```

Для точечного воспроизведения проблемного follow-up с сохранением реального гэпа между сообщениями:

```bash
sudo docker run --rm \
  --network crm-sales-bot-fork_default \
  -e API_KEY=change-me-in-production \
  -e E2E_HTTP_TIMEOUT_SECONDS=420 \
  -v "$PWD":/app \
  -w /app \
  crm-sales-bot-fork-bot \
  python3 -u live_api_real_payload_e2e.py \
    --events-file scripts/live_api_real_payload_scenarios/R11_second_screen_followup_hallucination_trace.json \
    --session BOT_R11_TRACE_test \
    --rebase-timestamps-to-now \
    --respect-input-gaps \
    --max-gap-sleep-ms 900000
```

Скрипт сам шлёт header `X-E2E-Debug-Trace: 1`, поэтому в `results/live_api_real_payload/.../trace.json` сохраняются сырой request/response и `_debug` payload для разбора.

Список сценариев:

- `R01`: счет вечером, комплект без денежного ящика, ИИН/номер, бонусы, телефон vs ноутбук, тестовый период.
- `R02`: `Стандарт+`, рассрочка на 24 месяца, другой город, UMAG, миграция базы, раздельная рассрочка программы и оборудования.
- `R03`: доставка в регион, отказ от предоплаты, страх мошенничества, Astana Hub/сайт/Instagram, конфиденциальность клиентов, follow-up.
- `R04`: смешанный RU/KZ, полный список оборудования, ненужные весы, не продуктовый магазин, раздражение от общих ответов, отказ от реквизитов.
- `R05`: вопрос про WhatsApp, честное признание unknown KB, Kaspi/Halyk Market, роли, мобильный доступ, простые ответы, тестовый период.
- `R06`: один сотрудник, запуск только с телефона, без оборудования на старте, бонусы, тест, какой номер указывать.
- `R07`: магазин одежды и обуви, остатки/размеры/цвета, Excel + UMAG, онлайн-обучение, миграция, простота для продавца.
- `R08`: Pro vs Standard+, весы не нужны, техника отдельно от программы, обучение в комплекте, рассрочка, дозакупка.
- `R09`: хаотичный покупатель: счет, оборудование, 24 месяца, бонусы, фото реквизитов, отказ от мгновенной оплаты, переход в тест.
- `R10`: длинная сессия с разрывом по времени, ссылка на голосовое, предоплата, другой город, запрос на локальных клиентов, старт теста.
- `R11`: точечный трассировочный кейс: после вопроса про комплект PRO и рассрочку клиент через 14 минут уточняет про второй экран; нужен для разбора нерелевантного ответа про «времени мало».
