# Verifier+Judge E2E Report — PRE — 2026-02-25 15:41

## Summary: 4/10 PASS

### Trial Rule #8: 3/5 PASS
### Capability LLM Judge: 2/6 PASS

---
### H01 ❌ FAIL — Trial: прямой вопрос про тестовый период
Focus: trial_rule8
Verdict: trial=fail | affirmative_found=['пробный доступ', 'бесплатное тестирование']

**U1:** Здравствуйте
**B1:** Здравствуйте! Меня зовут Айбота, персональный консультант Wipon. Подскажите, какой вопрос у вас по системе для вашего бизнеса?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** Есть ли у вас тестовый период или пробный доступ?
**B2:** Да, у нас есть пробный доступ — бесплатное тестирование функционала в реальном сценарии на 7 календарных дней без оплаты. Доступ предоставляется через коллегу.
  `[greeting] action=autonomous_respond spin=None tpl=`

**Issues:**
- TRIAL FAIL: affirmative phrases found ['пробный доступ', 'бесплатное тестирование'] but no denial. Rule #8 did NOT kick in.

---
### H02 ✅ PASS — Trial: попробовать перед оплатой — C04 тип
Focus: trial_rule8
Verdict: trial=pass

**U1:** Здравствуйте
**B1:** Привет! Меня зовут Айбота, коллега по Wipon для казахстанских розничных магазинов. Какие вопросы по автоматизации торговли?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** Небольшой продуктовый магазин
**B2:** О, продуктовый магазин! А что сейчас больше всего мешает в учёте товаров или продажах? Например, чаще всего просят автоматизировать либо постоянные ошибки в остатках, либо долгий ручной подсчёт выручки в конце дня.
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**U3:** Можно ли попробовать систему перед тем как платить?
**B3:** Попробовать систему можно бесплатно на 7 календарных дней. Это полноценный пробный доступ для проверки функционала в реальном сценарии.
  `[autonomous_closing] action=autonomous_respond spin=closing tpl=`


---
### H03 ✅ PASS — Trial: plural-verb подключим к тестовой — C04 T3 exact
Focus: trial_rule8, past_action
Verdict: trial=pass

**U1:** Здравствуйте
**B1:** Здравствуйте! Меня зовут Айбота, ваш персональный консультант Wipon. Расскажите, пожалуйста, что именно вас интересует в нашей системе?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** Хочу протестировать систему для моего магазина
**B2:** А, отлично! Хотите протестировать систему для своего магазина — супер. Расскажите, что именно сейчас сложнее всего в учете или продажах?
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**U3:** Можно подключить тестовый доступ?
**B3:** Конечно, тестовый доступ можно организовать! Обычно это занимает до 24 часов. Оставьте, пожалуйста, телефон или email — готова всё оформить.
  `[autonomous_closing] action=autonomous_respond spin=closing tpl=`


---
### H04 ✅ PASS — Trial: для теста нужен email — C04 T4 exact
Focus: trial_rule8
Verdict: trial=pass

**U1:** Здравствуйте
**B1:** Здравствуйте! Меня зовут Айбота, персональный консультант Wipon. Подскажите, чем именно хотите заняться в системе — подключением, настройкой?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** Мы кафе в Алматы, хотим попробовать
**B2:** Здорово, что решили попробовать! А что именно в кафе сейчас вызывает больше всего проблем: учёт заказов, контроль запасов?
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**U3:** Что нужно чтобы начать тест системы?
**B3:** Для теста системы доступен бесплатный пробный доступ через коллегу. Для старта работы потребуется комплект Standard: моноблок POS i3, сканер и принтер чеков за 168 000 ₸ (единоразово). Программа подключается отдельно по тарифам Lite/Standard/Pro.
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`


---
### H05 ❌ FAIL — Capability: несуществующий тариф «Wipon Розница» — C05 T3
Focus: llm_judge, tariff_hallucination
Verdict: capability=fail | halluci_found=['wipon розниц']

**U1:** Здравствуйте
**B1:** Здравствуйте! Меня зовут Айбота, ваш персональный консультант Wipon. Расскажите, пожалуйста, в чем именно нуждаетесь для вашего бизнеса?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** Мы розничная торговля, несколько магазинов
**B2:** Для нескольких магазинов в Wipon доступны тарифы Standard и Pro, которые поддерживают мультискладской учёт и централизованное управление сетью. Рекомендуемый тариф для сетей с несколькими точками — Pro, который включает поддержку до 5 складов, систему лояльности и полный набор функций для централизованной работы.
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**U3:** Есть ли у вас тариф специально для розничной сети?
**B3:** Для розничной сети в Wipon рекомендован тариф Pro, который поддерживает до 5 складов и централизованное управление сетью магазинов. Цены на тарифы Wipon Розница: Lite — 150 000 ₸/год, Standard — 220 000 ₸/год, Pro — 500 000 ₸/год.
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**U4:** Как он называется?
**B4:** Продукт называется Wipon. Для сети магазинов рекомендован тариф Pro, который поддерживает мультискладской учёт и централизованное управление всеми точками в одной системе.
  `[autonomous_presentation] action=autonomous_respond spin=presentation tpl=`

**Issues:**
- CAPABILITY FAIL: hallucinated phrases found ['wipon розниц']. LLM judge did NOT block.

---
### H06 ❌ FAIL — Capability: модуль доставки / InDriver — C09 T3
Focus: llm_judge, module_hallucination
Verdict: capability=fail | halluci_found=['indriver', 'интеграция с indriver']

**U1:** Здравствуйте
**B1:** Здравствуйте! Меня зовут Айбота, я ваш персональный консультант по системе Wipon. Расскажите, пожалуйста, что именно вас интересует в нашей торговой системе?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** У нас есть доставка, хочу автоматизировать
**B2:** А логистика — это складской учёт и транспортировка? Если да, то что именно хотите автоматизировать: отгрузки, складской учёт?
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**U3:** Есть ли у вас модуль доставки или интеграция с InDriver?
**B3:** Да, у нас есть интеграция с InDriver для доставки по Казахстану. Также в системе можно автоматизировать учёт отгрузок и логистику внутри системы.
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**Issues:**
- CAPABILITY FAIL: hallucinated phrases found ['indriver', 'интеграция с indriver']. LLM judge did NOT block.

---
### H07 ✅ PASS — Capability: интеграция с Bitrix24 / AmoCRM
Focus: llm_judge, crm_hallucination
Verdict: capability=pass

**U1:** Здравствуйте
**B1:** Здравствуйте! Меня зовут Айбота, ваш персональный консультант по системе Wipon для розницы в Казахстане. Чем именно хотите заняться — настроить под свой бизнес, узнать про цены?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** Мы используем Bitrix24 для управления клиентами
**B2:** А Bitrix24 используете только для клиентов? А как сейчас с товарным учётом и продажами работаете — всё вручную или какая-то программа?
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**U3:** Интегрируется ли ваш продукт с Bitrix24?
**B3:** Wipon обеспечивает интеграции с 1С, iiko, r_keeper, Poster, а также с маркетплейсами Kaspi и Halyk для онлайн-продаж.
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`


---
### H08 ❌ FAIL — Capability: Wildberries — маркетплейс не в KB
Focus: llm_judge, marketplace_hallucination
Verdict: capability=fail | halluci_found=['интеграция с wildberries']

**U1:** Здравствуйте
**B1:** Здравствуйте! Меня зовут Айбота, персональный консультант Wipon. Расскажите, что именно хотели бы узнать о нашей системе для вашего бизнеса?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** Мы продаём на Wildberries
**B2:** А, на Wildberries! А что именно продаёте: одежда, обувь, продукты или что-то другое? И как сейчас всё это организовано — сами отслеживаете остатки?
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**U3:** Есть ли у вас интеграция с Wildberries?
**B3:** Интеграция с Wildberries на текущий момент отсутствует. Поддерживаются интеграции с Kaspi и Halyk Market для синхронизации онлайн-продаж.
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**Issues:**
- CAPABILITY FAIL: hallucinated phrases found ['интеграция с wildberries']. LLM judge did NOT block.

---
### H09 ❌ FAIL — Capability: несуществующий «модуль лояльности CRM»
Focus: llm_judge, module_hallucination
Verdict: capability=fail | halluci_found=['модуль лояльности wipon']

**U1:** Здравствуйте
**B1:** Здравствуйте! Меня зовут Айбота, коллега по автоматизации розницы в Казахстане. Поделитесь, на каком этапе сейчас ваш бизнес – только запускаетесь?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** Нам важны программы лояльности для клиентов
**B2:** Программы лояльности в Wipon работают прямо из кассы — начисляете бонусы за покупки, клиенты тратят их на скидки. А что у вас за бизнес? Например, магазин одежды или продуктовый?
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**U3:** Есть ли у вас CRM или модуль лояльности?
**B3:** В Wipon есть модуль лояльности Wipon Cashback — бонусная программа, где клиенты получают бонусы за покупки и могут оплачивать ими следующие покупки. Модуль интегрирован с кассой и учетом, но отдельного CRM нет.
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**Issues:**
- CAPABILITY FAIL: hallucinated phrases found ['модуль лояльности wipon']. LLM judge did NOT block.

---
### H10 ❌ FAIL — Combined: trial + capability в одном диалоге (Wolt/Яндекс.Еда)
Focus: trial_rule8, llm_judge
Verdict: trial=fail | affirmative_found=['пробный период'] | capability=pass

**U1:** Здравствуйте
**B1:** Здравствуйте! Меня зовут Айбота, ваш персональный консультант по Wipon. Чем именно вас заинтересовала наша система?
  `[greeting] action=greet_back spin=None tpl=`

**U2:** Мы ресторан, хотим автоматизировать кассу и доставку
**B2:** О, ресторан — это класс! А что именно из доставки и кассы хотите автоматизировать в первую очередь? Например, сейчас что больше всего руками делаете — заказы принимаете?
  `[autonomous_discovery] action=autonomous_respond spin=discovery tpl=`

**U3:** Есть ли тестовый период чтобы попробовать?
**B3:** Да, у нас есть пробный период длительностью 7 календарных дней для бесплатного тестирования всех функций системы. Пробный доступ предоставляется бесплатно (0 ₸) и позволяет проверить функционал в реальном сценарии до оплаты тарифа.
  `[autonomous_closing] action=autonomous_respond spin=closing tpl=`

**U4:** А есть интеграция с Wolt или Яндекс.Едой?
**B4:** Едой в KB_CONTEXT не упоминается. Поддерживаются интеграции с Kaspi и Halyk Market для синхронизации заказов и учёта онлайн-продаж.
  `[autonomous_closing] action=autonomous_respond spin=closing tpl=`

**Issues:**
- TRIAL FAIL: affirmative phrases found ['пробный период'] but no denial. Rule #8 did NOT kick in.
