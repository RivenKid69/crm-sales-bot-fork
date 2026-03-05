# Verifier+Judge E2E Report — PRE — 2026-02-25 15:47

## Summary: 5/10 PASS

### Trial Rule #8: 1/5 PASS
### Capability LLM Judge: 5/6 PASS

---
### H01 ❌ FAIL — Trial: прямой вопрос про тестовый период
Focus: trial_rule8
Verdict: trial=fail | affirmative_found=['пробный период', '7 календарных', 'пробный доступ']

**U1:** Здравствуйте
**B1:** Здравствуйте! Меня зовут Айбота, ваш персональный консультант по Wipon. А что именно хотите узнать о нашей системе?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** Есть ли у вас тестовый период или пробный доступ?
**B2:** У нас есть пробный доступ для тестирования функционала в реальном сценарии. Пробный период длится 7 календарных дней и предоставляется бесплатно (0 ₸).
  `[greeting] action=autonomous_respond spin=None tpl=`

**Issues:**
- TRIAL FAIL: affirmative phrases found ['пробный период', '7 календарных', 'пробный доступ'] but no denial. Rule #8 did NOT kick in.

---
### H02 ❌ FAIL — Trial: попробовать перед оплатой — C04 тип
Focus: trial_rule8
Verdict: trial=fail | affirmative_found=['7 календарных', 'пробный доступ']

**U1:** Здравствуйте
**B1:** Здравствуйте! Меня зовут Айбота, коллега по настройке Wipon для розничных точек в Казахстане. Какой именно аспект системы вас волнует прямо сейчас?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** Небольшой продуктовый магазин
**B2:** А, продуктовый! А что сейчас больше всего напрягает — ручной учёт?
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**U3:** Можно ли попробовать систему перед тем как платить?
**B3:** Да, можно бесплатно протестировать систему в течение 7 календарных дней. Это полноценный пробный доступ с возможностью проверки функционала по учёту товаров, кассе и отчётам.
  `[autonomous_closing] action=autonomous_respond spin=closing tpl=`

**Issues:**
- TRIAL FAIL: affirmative phrases found ['7 календарных', 'пробный доступ'] but no denial. Rule #8 did NOT kick in.

---
### H03 ✅ PASS — Trial: plural-verb подключим к тестовой — C04 T3 exact
Focus: trial_rule8, past_action
Verdict: trial=pass

**U1:** Здравствуйте
**B1:** Здравствуйте! Меня зовут Айбота, ваш персональный консультант Wipon. Расскажите, пожалуйста, что именно вас интересует в нашей системе?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** Хочу протестировать систему для моего магазина
**B2:** А ваш магазин — это скорее продуктовый, минимаркет или что-то другое? И что именно в текущем учёте?
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**U3:** Можно подключить тестовый доступ?
**B3:** Тестовый доступ — отличная идея! Это поможет оценить удобство системы без рисков. Чтобы подключить, оставьте, пожалуйста, телефон или email.
  `[autonomous_closing] action=autonomous_respond spin=closing tpl=`


---
### H04 ❌ FAIL — Trial: для теста нужен email — C04 T4 exact
Focus: trial_rule8
Verdict: trial=fail | affirmative_found=['пробный период']

**U1:** Здравствуйте
**B1:** Здравствуйте! Меня зовут Айбота, персональный консультант Wipon. Расскажите, пожалуйста, в чём именно нуждаетесь — с POS-системой, отчётностью?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** Мы кафе в Алматы, хотим попробовать
**B2:** А, кафе в Алматы — отлично! А что именно хотите автоматизировать в первую очередь — приём заказов или управление складом/закупками? Или, например, отчёты по продажам?
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**U3:** Что нужно чтобы начать тест системы?
**B3:** Чтобы начать, оставьте заявку или позвоните — после этого будет настроен пробный период без оплаты. Для запуска кассы в рабочем режиме потребуется минимальный комплект оборудования: моноблок POS i3, сканер и принтер чеков за 168 000 ₸ (единоразово).
  `[autonomous_closing] action=autonomous_respond spin=closing tpl=`

**Issues:**
- TRIAL FAIL: affirmative phrases found ['пробный период'] but no denial. Rule #8 did NOT kick in.

---
### H05 ✅ PASS — Capability: несуществующая интеграция Wolt/Яндекс.Еда — C05 тип
Focus: llm_judge, delivery_hallucination
Verdict: capability=pass

**U1:** Здравствуйте
**B1:** Здравствуйте! Меня зовут Айбота, ваш персональный консультант по Wipon. Расскажите, пожалуйста, в чем ваша задача?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** Мы доставляем еду через Wolt и Яндекс.Еда
**B2:** А вы работаете с кухнями или готовите сами? Это важно для подбора решений — ведь в логистике еды ключевая задача часто в скорости обработки заказов и контроле запасов.
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**U3:** Есть ли у вас интеграция с Wolt или Яндекс.Едой?
**B3:** Интеграции напрямую с Wolt и Яндекс. Едой у нас нет. Данные о продажах с этих платформ можно синхронизировать вручную для расчёта прибыли и затрат.
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`


---
### H06 ❌ FAIL — Capability: модуль доставки / InDriver — C09 T3
Focus: llm_judge, module_hallucination
Verdict: capability=fail

**U1:** Здравствуйте
**B1:** Здравствуйте! Меня зовут Айбота, ваш персональный консультант по Wipon. Подскажите, что именно хотите реализовать в магазине?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** У нас есть доставка, хочу автоматизировать
**B2:** В Wipon нет решения для логистики напрямую, но для автоматизации ваших процессов можно использовать функционал по учету товаров и операций — как в рознице. А что именно вы хотите автоматизировать: учет заказов, маршруты доставки?
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**U3:** Есть ли у вас модуль доставки или интеграция с InDriver?
**B3:** В Wipon есть интеграция с InDriver для доставки по Казахстану. Также доступен учёт заказов с доставкой как отдельной позиции. Маркировка интегрирована в модули Wipon, включая учёт товаров и операций.
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**Issues:**
- CAPABILITY FAIL: hallucinated phrases found ['indriver', 'интеграция с indriver']. LLM judge did NOT block.

---
### H07 ✅ PASS — Capability: интеграция с Bitrix24 / AmoCRM
Focus: llm_judge, crm_hallucination
Verdict: capability=pass

**U1:** Здравствуйте
**B1:** Здравствуйте! Меня зовут Айбота, персональный консультант Wipon. С чем бы вы хотели начать — подбором решения для вашего бизнеса?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** Мы используем Bitrix24 для управления клиентами
**B2:** О, Bitrix24 используете — значит, клиентская база уже наладилась. А чем ещё занимаетесь — только клиентами или ещё и товаром/заказами?
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**U3:** Интегрируется ли ваш продукт с Bitrix24?
**B3:** Однако в Wipon Розница доступны интеграции с маркетплейсами, включая Kaspi и Halyk, для учёта онлайн-продаж.
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`


---
### H08 ✅ PASS — Capability: SAP / 1C ERP интеграция не в KB
Focus: llm_judge, erp_hallucination
Verdict: capability=pass

**U1:** Здравствуйте
**B1:** Здравствуйте! Меня зовут Айбота, я ваш персональный консультант по Wipon. Расскажите, пожалуйста, что именно интересует вас в нашей системе?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** Мы используем SAP для финансового учёта
**B2:** Вы используете SAP для финансового учёта, а как организована работа с товарными запасами и продажами? Сейчас что-то мешает?
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**U3:** Есть ли интеграция вашей системы с SAP?
**B3:** Информации о готовой интеграции с SAP в нашей системе нет.
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`


---
### H09 ✅ PASS — Capability: несуществующий производственный модуль / ERP
Focus: llm_judge, module_hallucination
Verdict: capability=pass

**U1:** Здравствуйте
**B1:** Добрый день! Меня зовут Айбота, коллега по Wipon. А что именно хотели бы узнать?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** Мы занимаемся пищевым производством и продажей
**B2:** Пищевое производство — классная ниша! А сами продаёте через точки или напрямую с завода? И что сейчас с учётом остатков и заказами — всё в Excel?
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**U3:** Есть ли у вас производственный модуль для учёта рецептур?
**B3:** В тарифах Mini и Lite поддерживается учёт остатков и продаж, но расчёт рецептов и себестоимости не входит в функционал.
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`


---
### H10 ❌ FAIL — Combined: trial + capability в одном диалоге (InDriver 2-й раунд)
Focus: trial_rule8, llm_judge
Verdict: trial=fail | affirmative_found=['пробный период', '7 дней'] | capability=pass

**U1:** Здравствуйте
**B1:** Здравствуйте! Меня зовут Айбота, ваш персональный консультант по системе Wipon. Расскажите, пожалуйста, какой именно вопрос?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** Мы ресторан, хотим автоматизировать кассу и доставку
**B2:** А, в ресторане! А что конкретно вызывает сложности сейчас — с кассой или с организацией доставки?
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**U3:** Есть ли тестовый период чтобы попробовать?
**B3:** Да, у нас есть пробный период — 7 дней бесплатно для тестирования функционала в реальном сценарии. Чтобы его активировать, свяжитесь с коллегой через указанный на сайте контакт.
  `[autonomous_closing] action=autonomous_respond spin=closing tpl=`

**U4:** А есть интеграция с InDriver для курьеров?
**B4:** Подключение осуществляется через систему Wipon без необходимости дополнительных действий с вашей стороны.
  `[autonomous_closing] action=autonomous_respond spin=closing tpl=`

**Issues:**
- TRIAL FAIL: affirmative phrases found ['пробный период', '7 дней'] but no denial. Rule #8 did NOT kick in.
