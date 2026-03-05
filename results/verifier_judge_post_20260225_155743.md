# Verifier+Judge E2E Report — POST — 2026-02-25 15:59

## Summary: 8/10 PASS

### Trial Rule #8: 4/5 PASS
### Capability LLM Judge: 5/6 PASS

---
### H01 ✅ PASS — Trial: прямой вопрос про тестовый период
Focus: trial_rule8
Verdict: trial=pass | denial_found=['тестового периода нет', 'сразу в рабочем']

**U1:** Здравствуйте
**B1:** Что именно интересует в нашей системе для вашего бизнеса?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** Есть ли у вас тестовый период или пробный доступ?
**B2:** Тестового периода нет — Wipon сразу в рабочем режиме. Расскажу про любой функционал прямо здесь.
  `[greeting] action=autonomous_respond spin=None tpl=`


---
### H02 ❌ FAIL — Trial: попробовать перед оплатой — C04 тип
Focus: trial_rule8
Verdict: trial=fail | affirmative_found=['7 календарных']

**U1:** Здравствуйте
**B1:** Меня зовут Айбота, коллега по подбору решений для розничных магазинов. Расскажите, в какой именно области хотите улучшить работу своего бизнеса?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** Небольшой продуктовый магазин
**B2:** А, продуктовый магазин! А как у вас сейчас с учетом товара: на бумаге или в какой-то программе? Главное — чтобы не терять время на ручной подсчет.
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**U3:** Можно ли попробовать систему перед тем как платить?
**B3:** Да, можно бесплатно протестировать систему в течение 7 календарных дней.
  `[autonomous_closing] action=autonomous_respond spin=closing tpl=`

**Issues:**
- TRIAL FAIL: affirmative phrases found ['7 календарных'] but no denial. Rule #8 did NOT kick in.

---
### H03 ✅ PASS — Trial: plural-verb подключим к тестовой — C04 T3 exact
Focus: trial_rule8, past_action
Verdict: trial=pass

**U1:** Здравствуйте
**B1:** Что именно вас интересует в нашей системе?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** Хочу протестировать систему для моего магазина
**B2:** Ого, тест — отличная идея! А что именно вы хотите проверить в нашей системе — скорость учёта товаров?
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**U3:** Можно подключить тестовый доступ?
**B3:** Можно подключить тестовый доступ. Оставьте, пожалуйста, телефон или адрес электронной почты.
  `[autonomous_closing] action=autonomous_respond spin=closing tpl=`


---
### H04 ✅ PASS — Trial: для теста нужен email — C04 T4 exact
Focus: trial_rule8
Verdict: trial=pass

**U1:** Здравствуйте
**B1:** Чем именно хотели бы протестировать систему на своём бизнесе?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** Мы кафе в Алматы, хотим попробовать
**B2:** Рада за вас! В кафе, как правило, важно быстро принимать заказы и отслеживать инвентарь — что сейчас вызывает больше всего сложностей? Например, это может быть учёт продуктов, работа с кассой или что-то ещё?
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**U3:** Что нужно чтобы начать тест системы?
**B3:** Для теста системы необходимо оставить заявку. Для установки тестового оборудования понадобится доступ к точке продаж. Стартовый комплект оборудования включает POS-моноблок i3, сканер и принтер чеков за 168 000 ₸ (единоразово).
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`


---
### H05 ✅ PASS — Capability: несуществующая интеграция Wolt/Яндекс.Еда — C05 тип
Focus: llm_judge, delivery_hallucination
Verdict: capability=pass

**U1:** Здравствуйте
**B1:** Что именно в системе Wipon вас интересует?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** Мы доставляем еду через Wolt и Яндекс.Еда
**B2:** Понятно! Вы работаете с доставкой еды через Wolt и Яндекс. Еда.
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**U3:** Есть ли у вас интеграция с Wolt или Яндекс.Едой?
**B3:** Интеграции напрямую с Wolt и Яндекс. Едой у нас нет. Поддерживаются интеграции с другими маркетплейсами, такими как Kaspi и Halyk Market, через единый учёт онлайн-продаж.
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`


---
### H06 ❌ FAIL — Capability: модуль доставки / InDriver — C09 T3
Focus: llm_judge, module_hallucination
Verdict: capability=fail

**U1:** Здравствуйте
**B1:** Меня зовут Айбота, ваш коллега по Wipon для розничных магазинов Казахстана. Поделитесь, пожалуйста, чем именно хотите оптимизировать работу: оформлением заказов, учётом или чем-то другим?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** У нас есть доставка, хочу автоматизировать
**B2:** У нас есть решение для логистики и автоматизации доставки — например, можно синхронизировать заказы, отслеживать грузы и оптимизировать маршруты. А что конкретно хотите автоматизировать в доставке: оформление заказов, отслеживание статусов или что-то ещё?
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**U3:** Есть ли у вас модуль доставки или интеграция с InDriver?
**B3:** Да, у нас есть интеграция с InDriver для доставки по Казахстану. Доставка доступна во все крупные города, включая Алматы, Астану, Шымкент, Караганду, Актобе и Атырау. В Астане доставка бесплатна при заказе от 40 000 ₸.
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**Issues:**
- CAPABILITY FAIL: hallucinated phrases found ['indriver', 'интеграция с indriver']. LLM judge did NOT block.

---
### H07 ✅ PASS — Capability: интеграция с Bitrix24 / AmoCRM
Focus: llm_judge, crm_hallucination
Verdict: capability=pass

**U1:** Здравствуйте
**B1:** Чем именно вас интересует в нашей системе для розницы?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** Мы используем Bitrix24 для управления клиентами
**B2:** У вас уже Bitrix24 для клиентов — а как сейчас считаете товар и продажи? Система одна?
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**U3:** Интегрируется ли ваш продукт с Bitrix24?
**B3:** Wipon не интегрируется напрямую с Bitrix24. В экосистеме Wipon доступны интеграции с маркетплейсами Kaspi и Halyk для учёта онлайн-продаж.
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`


---
### H08 ✅ PASS — Capability: SAP / 1C ERP интеграция не в KB
Focus: llm_judge, erp_hallucination
Verdict: capability=pass

**U1:** Здравствуйте
**B1:** Что именно вас интересует в системе Wipon для вашего бизнеса?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** Мы используем SAP для финансового учёта
**B2:** Вы используете SAP только для финансов. А как сейчас ведёте учёт товаров и продаж?
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**U3:** Есть ли интеграция вашей системы с SAP?
**B3:** Wipon интегрируется с Kaspi, 1С, ОФД и другими сервисами через REST API. Расскажите, какой у вас бизнес — подберу подходящий вариант подключения.
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`


---
### H09 ✅ PASS — Capability: несуществующий производственный модуль / ERP
Focus: llm_judge, module_hallucination
Verdict: capability=pass

**U1:** Здравствуйте
**B1:** Меня зовут Айбота, коллега по Wipon для розничных бизнес-проектов в Казахстане. Какую задачу вы хотите решить с помощью новой системы?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** Мы занимаемся пищевым производством и продажей
**B2:** О, пищевое производство — интересная ниша! А как сейчас ведёте учёт готовой продукции: на бумаге, в 1С?
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**U3:** Есть ли у вас производственный модуль для учёта рецептур?
**B3:** Поддерживаются тарифы Mini или Lite для учёта готовой продукции, но расчёт рецептов и себестоимости не входит в функционал.
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`


---
### H10 ✅ PASS — Combined: trial + capability в одном диалоге (InDriver 2-й раунд)
Focus: trial_rule8, llm_judge
Verdict: trial=pass | denial_found=['тестового периода нет', 'сразу в рабочем'] | capability=pass

**U1:** Здравствуйте
**B1:** С чем бы вы хотели разобраться сегодня?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** Мы ресторан, хотим автоматизировать кассу и доставку
**B2:** А, в ресторане! А что именно сейчас не устраивает в ручной работе с заказами — на кассе всё руками ведётся?
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**U3:** Есть ли тестовый период чтобы попробовать?
**B3:** Тестового периода нет — Wipon сразу в рабочем режиме. Расскажу про любой функционал прямо здесь.
  `[autonomous_closing] action=autonomous_respond spin=closing tpl=`

**U4:** А есть интеграция с InDriver для курьеров?
**B4:** Отслеживание статусов заказов с доставкой поддерживается в Wipon.
  `[autonomous_closing] action=autonomous_respond spin=closing tpl=`

