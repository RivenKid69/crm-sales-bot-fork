# Сравнение диалогов: PRE vs POST1

- **PRE**: 13/15 PASS
- **POST1**: 12/15 PASS

---
## T01: Decision amnesia — бизнес уже назван, бот не застревает в discovery
**Фокус**: decision_history
**PRE**: PASS | **POST1**: PASS

### Auto-checks
- `left_discovery_by_T5`: PRE=✅ POST1=✅
- `no_repeat_business_question`: PRE=✅ POST1=✅

### PRE диалог (6 ходов)

**T1** [greeting] intent=greeting
> **User**: Привет
> **Bot**: Меня зовут Айбота, я ваш персональный консультант Wipon. Расскажите, что вас интересует в системе для вашего магазина?

**T2** [autonomous_discovery] intent=situation_provided
> **User**: У меня сеть из 3 продуктовых магазинов в Алматы
> **Bot**: Три точки в Алматы — это отличный масштаб для единого управления. Скажите, что сейчас в работе больше всего занимает времени?

**T3** [autonomous_presentation] intent=need_expressed
> **User**: Нам нужна единая система учёта, что предложите?
> **Bot**: Wipon объединит все три магазина в одну систему с общим складом и аналитикой. Скажите, как вы сейчас контролируете остатки на всех точках?

**T4** [autonomous_presentation] intent=situation_provided
> **User**: Да, всё верно, 3 магазина
> **Bot**: Радостно слышу подтверждение. Wipon даст вам полную прозрачность по трём точкам в одном окне. Что сейчас вызывает больше всего сложностей при управлении сетью?

**T5** [autonomous_presentation] intent=question_features
> **User**: Расскажите подробнее про функции
> **Bot**: Уточните, пожалуйста, что вы имеете в виду под «Pro»:
1) Комплект Pro
2) Тариф Pro
Ответьте номером 1-3 или напишите вариант словами.

**T6** [autonomous_negotiation] intent=situation_provided
> **User**: А какой тариф подойдёт для 3 точек?
> **Bot**: Тариф Pro стоит 500 000 тенге в год и поддерживает до 5 точек с неограниченным количеством товаров. В него включена расширенная аналитика, план закупок и три оптовые цены. Расскажите, планируете ли вы в будущем расширять сеть за пределы пяти магазинов?

### POST1 диалог (6 ходов)

**T1** [greeting] intent=greeting
> **User**: Привет
> **Bot**: Привет! Меня зовут Айбота, я ваш персональный консультант Wipon. Что именно вас интересует в нашей системе?

**T2** [autonomous_discovery] intent=situation_provided
> **User**: У меня сеть из 3 продуктовых магазинов в Алматы
> **Bot**: Три точки — отличное начало. Wipon позволяет управлять всеми магазинами из одного кабинета. А что сейчас больше всего напрягает в работе?

**T3** [autonomous_presentation] intent=need_expressed
> **User**: Нам нужна единая система учёта, что предложите?
> **Bot**: Для сети магазинов идеально подойдет тариф с безлимитным количеством товаров и управлением всеми точками из одного кабинета. Хотите узнать подробнее, как это работает в вашем случае?

**T4** [autonomous_presentation] intent=situation_provided
> **User**: Да, всё верно, 3 магазина
> **Bot**: Отлично, три точки — это как раз тот случай, когда нужно видеть все продажи и остатки в одном окне. Скажите, а как сейчас у вас организована передача данных между магазинами и центром?

**T5** [autonomous_presentation] intent=question_features
> **User**: Расскажите подробнее про функции
> **Bot**: Уточните, пожалуйста, что вы имеете в виду под «Pro»:
1) Комплект Pro
2) Тариф Pro
Ответьте номером 1-3 или напишите вариант словами.

**T6** [autonomous_presentation] intent=situation_provided
> **User**: А какой тариф подойдёт для 3 точек?
> **Bot**: Тариф Pro стоит 500 000 ₸ в год, включает до 5 точек, неограниченные товары и полную бухгалтерию. Есть возможность оплаты в рассрочку, условия уточняются индивидуально. Как вам такой формат оплаты для старта?

### Сравнение состояний
```
PRE:   greeting → autonomous_discovery → autonomous_presentation → autonomous_presentation → autonomous_presentation → autonomous_negotiation
POST1: greeting → autonomous_discovery → autonomous_presentation → autonomous_presentation → autonomous_presentation → autonomous_presentation
```
**⚠️ РАЗЛИЧАЮТСЯ**

---
## T02: Decision amnesia — обсуждение цен, но decision не видит контекста
**Фокус**: decision_history
**PRE**: PASS | **POST1**: PASS

### Auto-checks
- `has_prices`: PRE=✅ POST1=✅
- `not_in_discovery_after_T5`: PRE=✅ POST1=✅

### PRE диалог (7 ходов)

**T1** [autonomous_discovery] intent=situation_provided
> **User**: Здравствуйте, у меня один магазин электроники
> **Bot**: Здорово, электроника требует точного учёта серийных номеров и гарантий. Расскажите, с какими сложностями сталкиваетесь сейчас в работе?

**T2** [autonomous_discovery] intent=question_tariff_mini
> **User**: Сколько стоит Mini?
> **Bot**: Тариф Mini стоит 5 000 тенге в месяц за одну точку. Это базовый вариант с онлайн-кассой и фискализацией. Для электроники с серийным учётом обычно берут тарифы Standard или Pro.

**T3** [autonomous_discovery] intent=question_tariff_lite
> **User**: А Lite?
> **Bot**: Уточните, пожалуйста, что вы имеете в виду под «Pro»:
1) Комплект Pro
2) Тариф Pro
Ответьте номером 1-3 или напишите вариант словами.

**T4** [autonomous_discovery] intent=question_tariff_comparison
> **User**: А можно сравнить все тарифы?
> **Bot**: Тариф Lite стоит 150 000 тенге в год для одной торговой точки. В него включена номенклатура без ограничений, интеграция с POS-терминалами и Wipon ОФД. Обучение сотрудников включено в стоимость тарифа и проводится на запуске без доплаты.

**T5** [autonomous_qualification] intent=rejection
> **User**: Что входит в Standard помимо того что в Lite?
> **Bot**: В тарифе Standard уже доступны три торговые точки вместо одной и возможность вести отдельный прайс-лист для оптовых клиентов. Номенклатура в обоих вариантах без ограничений.

**T6** [autonomous_qualification] intent=pricing_details
> **User**: Standard за 220 тысяч — это в год?
> **Bot**: Да, это годовая стоимость. В тариф Standard уже включено до трёх торговых точек и оптовые цены.

**T7** [autonomous_qualification] intent=question_equipment_general
> **User**: А оборудование отдельно покупать?
> **Bot**: Да, программа и оборудование оплачиваются отдельно. Комплект техники можно собрать от 168 000 тенге или использовать вашу технику.

### POST1 диалог (7 ходов)

**T1** [autonomous_discovery] intent=situation_provided
> **User**: Здравствуйте, у меня один магазин электроники
> **Bot**: Отлично, электроника — это удобно, ведь в Wipon есть учёт серийных номеров и гарантий. А что сейчас больше всего напрягает в работе с кассой или остатками?

**T2** [autonomous_discovery] intent=question_tariff_mini
> **User**: Сколько стоит Mini?
> **Bot**: Тариф Mini стоит 5 000 тенге в месяц за одну точку. В него входит онлайн-касса и фискализация чеков. Хотите узнать, какие возможности есть в более расширенных годовых тарифах?

**T3** [autonomous_discovery] intent=question_tariff_lite
> **User**: А Lite?
> **Bot**: Тариф Lite стоит 150 000 тенге в год для одной точки, там безлимитная номенклатура и включено обучение. В нём есть всё для полноценного учёта, включая интеграцию с терминалами.

**T4** [autonomous_discovery] intent=pricing_comparison
> **User**: А можно сравнить все тарифы?
> **Bot**: Тариф Standard стоит 220 000 тенге в год, поддерживает до трёх торговых точек, до трёх складов, розничную и оптовую цену, а также расширенную аналитику. Обучение включено в тариф.

**T5** [autonomous_qualification] intent=rejection
> **User**: Что входит в Standard помимо того что в Lite?
> **Bot**: В Standard вы получите поддержку до трёх точек и возможность вести отдельный оптовый прайс-лист, что важно для роста.

**T6** [autonomous_qualification] intent=pricing_details
> **User**: Standard за 220 тысяч — это в год?
> **Bot**: Да, это годовая подписка. В Standard уже включено обучение и поддержка до трёх точек.

**T7** [autonomous_qualification] intent=question_equipment_general
> **User**: А оборудование отдельно покупать?
> **Bot**: Да, оборудование в Wipon всегда приобретается отдельно от программы, так как это позволяет выбрать только то, что нужно под ваши задачи.

### Сравнение состояний
```
PRE:   autonomous_discovery → autonomous_discovery → autonomous_discovery → autonomous_discovery → autonomous_qualification → autonomous_qualification → autonomous_qualification
POST1: autonomous_discovery → autonomous_discovery → autonomous_discovery → autonomous_discovery → autonomous_qualification → autonomous_qualification → autonomous_qualification
```
Одинаковые

---
## T03: Decision amnesia — возражение 'дорого', decision не видит историю
**Фокус**: decision_history
**PRE**: PASS | **POST1**: PASS

### Auto-checks
- `no_premature_closing`: PRE=✅ POST1=✅
- `offers_alternative`: PRE=✅ POST1=✅

### PRE диалог (6 ходов)

**T1** [autonomous_discovery] intent=situation_provided
> **User**: Добрый день, у меня магазин косметики
> **Bot**: Магазин косметики — отличный формат, в Wipon есть учёт штрихкодов и акций. Расскажите, что сейчас мешает работать быстрее?

**T2** [autonomous_discovery] intent=question_tariff_standard
> **User**: Сколько стоит Standard?
> **Bot**: Тариф Standard стоит 220 000 тенге в год и включает до трёх торговых точек без ограничений по товарам. Вам подойдёт этот вариант для вашего магазина косметики?

**T3** [autonomous_objection_handling] intent=objection_price
> **User**: 220 тысяч?! Это очень дорого для одного магазина
> **Bot**: Понимаю ваши опасения, для одного магазина сумма действительно кажется ощутимой. Стандарт включает три точки и полный складской учёт, что окупается за счёт контроля остатков и аналитики. А какой формат работы вам сейчас ближе: просто касса?

**T4** [autonomous_objection_handling] intent=budget_question
> **User**: У меня бюджет максимум 10 тысяч в месяц
> **Bot**: При бюджете 5 000 тенге в месяц идеально подойдёт тариф Mini за 5 000 тенге/мес с базовой кассой. Он закроет фискализацию и учёт продаж без лишних затрат.

**T5** [autonomous_objection_handling] intent=pricing_details
> **User**: А что входит в Mini за 5000?
> **Bot**: Точную стоимость для вашего случая уточню у коллег и вернусь с ответом.

**T6** [autonomous_objection_handling] intent=question_scalability
> **User**: А можно потом перейти на Standard когда бизнес вырастет?
> **Bot**: Да, переход с Mini на Standard доступен в любой момент без потери данных. Это удобно для старта с базового тарифа и дальнейшего расширения по мере роста.

### POST1 диалог (6 ходов)

**T1** [autonomous_discovery] intent=situation_provided
> **User**: Добрый день, у меня магазин косметики
> **Bot**: Магазин косметики — отлично, Wipon отлично подходит для такой ниши. А что сейчас больше всего напрягает в учёте или кассе?

**T2** [autonomous_discovery] intent=question_tariff_standard
> **User**: Сколько стоит Standard?
> **Bot**: Тариф Standard стоит 220 000 тенге в год и включает до трёх торговых точек.

**T3** [autonomous_discovery] intent=objection_price
> **User**: 220 тысяч?! Это очень дорого для одного магазина
> **Bot**: Поняла, сумма кажется ощутимой. А сколько вы планируете потратить на отдельную кассу и программиста?

**T4** [autonomous_discovery] intent=budget_question
> **User**: У меня бюджет максимум 10 тысяч в месяц
> **Bot**: Бюджет в 10 тысяч в месяц вполне реален для старта с тарифом Mini за 5 000 тенге/мес, это даст вам онлайн-кассу и базовый учёт.

**T5** [autonomous_qualification] intent=pricing_details
> **User**: А что входит в Mini за 5000?
> **Bot**: Уточните, пожалуйста, что вы имеете в виду под «Mini»:
1) Тариф Mini
2) Комплект Mini
Ответьте номером 1-3 или напишите вариант словами.

**T6** [autonomous_qualification] intent=question_scalability
> **User**: А можно потом перейти на Standard когда бизнес вырастет?
> **Bot**: Да, переход с Mini на Standard возможен в любой момент без потери данных. Товары, остатки и история сохранятся, нужно просто доплатить разницу за тариф.

### Сравнение состояний
```
PRE:   autonomous_discovery → autonomous_discovery → autonomous_objection_handling → autonomous_objection_handling → autonomous_objection_handling → autonomous_objection_handling
POST1: autonomous_discovery → autonomous_discovery → autonomous_discovery → autonomous_discovery → autonomous_qualification → autonomous_qualification
```
**⚠️ РАЗЛИЧАЮТСЯ**

---
## T04: Premature transition — нет business_type, нельзя уходить из discovery
**Фокус**: graduation_criteria
**PRE**: FAIL | **POST1**: FAIL

### Auto-checks
- `stays_discovery_until_business`: PRE=❌ POST1=❌

### PRE диалог (5 ходов)

**T1** [greeting] intent=greeting
> **User**: Привет
> **Bot**: Меня зовут Айбота, я ваш персональный консультант Wipon. Расскажите, что вас интересует?

**T2** [autonomous_discovery] intent=consultation_request
> **User**: Хочу подключить кассовую программу
> **Bot**: Wipon интегрируется с Kaspi, 1С, ОФД и другими сервисами через REST API. Расскажите, какой у вас бизнес — подберу подходящий вариант подключения.

**T3** [autonomous_qualification] intent=situation_provided
> **User**: У меня магазин обуви, одна точка
> **Bot**: Отлично, для одного магазина обуви у нас есть подходящие решения. Скажите, сколько примерно товаров у вас в ассортименте?

**T4** [autonomous_qualification] intent=info_provided
> **User**: Да, в Астане
> **Bot**: Астана — прекрасный выбор для старта. Подскажите, планируете ли вы расширяться в будущем?

**T5** [autonomous_qualification] intent=question_tariff_comparison
> **User**: Какой тариф мне подойдёт?
> **Bot**: Для одного магазина обуви чаще выбирают тариф Lite за 150 000 тенге в год или Standard за 220 000 тенге/год, если нужен расширенный учёт. Какой функционал для вас сейчас важнее: простая касса?

### POST1 диалог (5 ходов)

**T1** [greeting] intent=greeting
> **User**: Привет
> **Bot**: Меня зовут Айбота, я ваш персональный консультант Wipon. Расскажите, что именно вас интересует в нашей системе?

**T2** [autonomous_discovery] intent=question_tis_general
> **User**: Хочу подключить кассовую программу
> **Bot**: Wipon интегрируется с Kaspi, 1С, ОФД и другими сервисами через REST API. Расскажите, какой у вас бизнес — подберу подходящий вариант подключения.

**T3** [autonomous_discovery] intent=situation_provided
> **User**: У меня магазин обуви, одна точка
> **Bot**: Магазин обуви — отличный формат для Wipon. А что сейчас в учёте вызывает больше всего сложностей?

**T4** [autonomous_discovery] intent=info_provided
> **User**: Да, в Астане
> **Bot**: Отлично, в Астане мы часто помогаем магазинам обуви. А как сейчас считаете выручку и ведете остатки товаров?

**T5** [autonomous_discovery] intent=question_tariff_comparison
> **User**: Какой тариф мне подойдёт?
> **Bot**: Для магазина обуви с одной точкой подойдёт тариф Lite за 150 000 ₸ в год. В него включены учёт размеров, интеграция с ОФД и базовые операции продаж. Если нужна расширенная аналитика или работа с несколькими складами (до 3), можно рассмотреть тариф Standard за 220 000 ₸ в год.

### Сравнение состояний
```
PRE:   greeting → autonomous_discovery → autonomous_qualification → autonomous_qualification → autonomous_qualification
POST1: greeting → autonomous_discovery → autonomous_discovery → autonomous_discovery → autonomous_discovery
```
**⚠️ РАЗЛИЧАЮТСЯ**

---
## T05: Late transition — все данные discovery собраны, но бот застрял
**Фокус**: graduation_criteria
**PRE**: PASS | **POST1**: PASS

### Auto-checks
- `left_discovery_by_T4`: PRE=✅ POST1=✅

### PRE диалог (6 ходов)

**T1** [autonomous_discovery] intent=situation_provided
> **User**: Здравствуйте, у нас сеть магазинов одежды — 4 точки в Алматы
> **Bot**: Четыре точки в Алматы — отличный масштаб для единой системы. Расскажите, какая задача сейчас стоит на первом месте в управлении сетью?

**T2** [autonomous_discovery] intent=info_provided
> **User**: Да, розничная торговля, женская одежда
> **Bot**: Женская одежда — отличная ниша для розничной системы. Как сейчас ведете учёт остатков и продаж по четырем точкам?

**T3** [autonomous_discovery] intent=situation_provided
> **User**: Нас 15 сотрудников, 4 кассы
> **Bot**: Пятнадцать сотрудников и четыре кассы — это уже серьёзный масштаб. Что сейчас больше всего отнимает время у команды в учёте?

**T4** [autonomous_qualification] intent=info_provided
> **User**: Сейчас всё на бумаге ведём, хотим автоматизировать
> **Bot**: Поняла, переход с бумаги на автоматизацию — отличное решение для вашего масштаба. Система Wipon синхронизирует кассы и склад в реальном времени, так что остатки всегда будут точными. У вас уже есть примерный бюджет на внедрение?

**T5** [autonomous_presentation] intent=budget_question
> **User**: Бюджет примерно 300 тысяч в год готовы выделить
> **Bot**: Бюджет 300 тысяч в год полностью покрывает тариф Standard — это 220 000 тенге/год за три точки, но у вас четыре. Для четвёртой точки можно рассмотреть тариф Pro за 500 000 тенге/год или добавить отдельную подписку. Какой вариант управления сетью вам ближе?

**T6** [autonomous_presentation] intent=situation_provided
> **User**: Расскажите что у вас есть для сети магазинов
> **Bot**: Уточните, пожалуйста, что вы имеете в виду под «Pro»:
1) Комплект Pro
2) Тариф Pro
Ответьте номером 1-3 или напишите вариант словами.

### POST1 диалог (6 ходов)

**T1** [autonomous_discovery] intent=situation_provided
> **User**: Здравствуйте, у нас сеть магазинов одежды — 4 точки в Алматы
> **Bot**: Четыре точки в Алматы — отличный масштаб для старта. А какие процессы сейчас занимают больше всего времени у кассиров или владельца?

**T2** [autonomous_discovery] intent=info_provided
> **User**: Да, розничная торговля, женская одежда
> **Bot**: Женская одежда — это всегда много размеров и сезонность. Как вы сейчас контролируете остатки, чтобы не было расхождений между четырьмя точками?

**T3** [autonomous_discovery] intent=situation_provided
> **User**: Нас 15 сотрудников, 4 кассы
> **Bot**: Пятнадцать сотрудников и четыре кассы — отличный масштаб для роста. Сейчас что самое сложное в управлении такой сетью и передаче данных между точками?

**T4** [autonomous_presentation] intent=problem_revealed
> **User**: Сейчас всё на бумаге ведём, хотим автоматизировать
> **Bot**: Всё быстро, удобно и под ключ. Единая система: всё в одном месте

**T5** [autonomous_presentation] intent=budget_question
> **User**: Бюджет примерно 300 тысяч в год готовы выделить
> **Bot**: Wipon Consulting ведёт форму 300 (НДС) под ключ: расчёт, заполнение, подача через ЭЦП и контроль приёма в КГД. Бюджет около 100 000 ₸ достижим при наличии ноутбука.

**T6** [autonomous_presentation] intent=situation_provided
> **User**: Расскажите что у вас есть для сети магазинов
> **Bot**: Для сети одежды идеально подойдёт тариф Pro с управлением до пяти точек из одного аккаунта. Это позволит централизованно менять цены и видеть остатки на всех складах. Рассказать подробнее о возможностях кассы для вашего формата?

### Сравнение состояний
```
PRE:   autonomous_discovery → autonomous_discovery → autonomous_discovery → autonomous_qualification → autonomous_presentation → autonomous_presentation
POST1: autonomous_discovery → autonomous_discovery → autonomous_discovery → autonomous_presentation → autonomous_presentation → autonomous_presentation
```
**⚠️ РАЗЛИЧАЮТСЯ**

---
## T06: Closing — бот должен собрать terminal data перед финалом
**Фокус**: graduation_criteria
**PRE**: PASS | **POST1**: PASS

### Auto-checks
- `asks_contact`: PRE=✅ POST1=✅
- `reached_closing`: PRE=✅ POST1=✅

### PRE диалог (5 ходов)

**T1** [autonomous_discovery] intent=situation_provided
> **User**: Здравствуйте, у меня аптека в Караганде
> **Bot**: Айбота, аптеки — это наша сильная сторона, мы знаем все нюансы. Скажите, что сейчас вызывает больше всего сложностей в учёте или кассе?

**T2** [autonomous_discovery] intent=question_features
> **User**: Мне нужна кассовая программа, что есть?
> **Bot**: У нас есть программа учёта и кассовых операций Wipon. Онлайн-касса Wipon бесплатна при использовании программы учёта. Программа подключается отдельно от оборудования по выбранному тарифу (доступны тарифы Mini, Lite, Standard, Pro).

**T3** [autonomous_negotiation] intent=price_question
> **User**: Standard подойдёт. Сколько стоит?
> **Bot**: Тариф Standard стоит 220 000 тенге в год и включает до 3 торговых точек. Также доступны неограниченные товары и сотрудники, до 3 складов, аналитика, план закупок, бухгалтерский и кадровый учет, интеграция с эквайрингом и обучение.

**T4** [autonomous_closing] intent=agreement
> **User**: Хорошо, беру Standard. Как подключиться?
> **Bot**: Уточните, пожалуйста, что вы имеете в виду под «Standard»:
1) Комплект Standard
2) Тариф Standard
Ответьте номером 1-3 или напишите вариант словами.

**T5** [autonomous_closing] intent=contact_provided
> **User**: Конечно, мой номер 87473334455
> **Bot**: Спасибо! Мой коллега позвонит вам в ближайшее время и согласует удобное время.

### POST1 диалог (5 ходов)

**T1** [autonomous_discovery] intent=situation_provided
> **User**: Здравствуйте, у меня аптека в Караганде
> **Bot**: Рада знакомству! Аптека — это отлично, у нас есть поддержка маркировки и учёта остатков. А какие процессы сейчас хотите автоматизировать в первую очередь?

**T2** [autonomous_discovery] intent=question_features
> **User**: Мне нужна кассовая программа, что есть?
> **Bot**: Расскажите подробнее о вашем бизнесе — это поможет подобрать оптимальное решение.

**T3** [autonomous_discovery] intent=question_tariff_standard
> **User**: Standard подойдёт. Сколько стоит?
> **Bot**: Тариф Standard стоит 220 000 тенге в год. В него входит учёт до трёх торговых точек и неограниченная номенклатура.

**T4** [autonomous_closing] intent=agreement
> **User**: Хорошо, беру Standard. Как подключиться?
> **Bot**: Уточните, пожалуйста, что вы имеете в виду под «Standard»:
1) Комплект Standard
2) Тариф Standard
Ответьте номером 1-3 или напишите вариант словами.

**T5** [autonomous_closing] intent=contact_provided
> **User**: Конечно, мой номер 87473334455
> **Bot**: Спасибо! Мой коллега позвонит вам в ближайшее время и согласует удобное время.

### Сравнение состояний
```
PRE:   autonomous_discovery → autonomous_discovery → autonomous_negotiation → autonomous_closing → autonomous_closing
POST1: autonomous_discovery → autonomous_discovery → autonomous_discovery → autonomous_closing → autonomous_closing
```
**⚠️ РАЗЛИЧАЮТСЯ**

---
## T07: Classifier context — 'да' как подтверждение (нужен контекст)
**Фокус**: classifier_history
**PRE**: PASS | **POST1**: PASS

### Auto-checks
- `da_understood`: PRE=✅ POST1=✅

### PRE диалог (7 ходов)

**T1** [autonomous_discovery] intent=situation_provided
> **User**: Здравствуйте, у меня продуктовый магазин
> **Bot**: Отлично, продуктовый магазин — Wipon отлично справится с учётом остатков и чеков. Скажите, а что сейчас в работе вызывает больше всего трудностей, с чего бы хотели начать?

**T2** [autonomous_qualification] intent=need_expressed
> **User**: Нужна кассовая программа с учётом остатков
> **Bot**: Поняла, для продуктового магазина это действительно база. Скажите, а сколько у вас сейчас торговых точек на руках?

**T3** [autonomous_qualification] intent=situation_provided
> **User**: У нас 2 точки, нужна единая база
> **Bot**: Для двух точек идеально подойдёт тариф Standard или комбинация Lite с доп точкой. А какой бюджет вы рассматриваете на запуск системы?

**T4** [autonomous_qualification] intent=question_tariff_standard
> **User**: Вы упомянули Standard тариф — в нём есть складской учёт?
> **Bot**: Да, в тарифе Standard точно есть складской учёт с контролем остатков и перемещений между точками. Это программный тариф 220 000 ₸ в год, который закрывает задачи для двух магазинов.

**T5** [autonomous_presentation] intent=agreement
> **User**: Да
> **Bot**: Отлично, тогда система объединит обе точки в единый учёт: остатки и продажи будут видны сразу в одном окне. Скажите, а сейчас вы уже пробовали подключать кассовое оборудование?

**T6** [autonomous_presentation] intent=question_multi_location
> **User**: А для двух точек подойдёт?
> **Bot**: Да, для двух точек тариф Standard подходит идеально: он включает до трёх точек и единый учёт всех продаж. Стоимость составит 220 000 тенге в год.

**T7** [autonomous_closing] intent=agreement
> **User**: Да, давайте оформим
> **Bot**: Отлично, я уже готова оформить всё для вас. Оставьте, пожалуйста, номер телефона для связи.

### POST1 диалог (7 ходов)

**T1** [autonomous_discovery] intent=situation_provided
> **User**: Здравствуйте, у меня продуктовый магазин
> **Bot**: Продуктовый магазин — отличный формат для Wipon. Скажите, что сейчас больше всего напрягает в работе: учёт остатков?

**T2** [autonomous_discovery] intent=need_expressed
> **User**: Нужна кассовая программа с учётом остатков
> **Bot**: Для продуктового магазина это идеальное решение — касса и учёт остатков работают в одном окне. Подскажите, сколько у вас сейчас точек продаж?

**T3** [autonomous_qualification] intent=situation_provided
> **User**: У нас 2 точки, нужна единая база
> **Bot**: Две точки — это уже растущий бизнес. Для единой базы идеально подойдёт тариф Standard, он включает до трёх точек. Скажите, планируете ли вы подключать оборудование сразу?

**T4** [autonomous_qualification] intent=question_tariff_standard
> **User**: Вы упомянули Standard тариф — в нём есть складской учёт?
> **Bot**: Да, в тарифе Standard есть полный складской учёт: от приёмки до списания и контроль остатков в реальном времени. Система показывает, где именно находится каждая позиция товара.

**T5** [autonomous_qualification] intent=agreement
> **User**: Да
> **Bot**: Отлично, значит складской учёт полностью закрывает ваши задачи. Расскажите, как сейчас ведётся учёт в двух точках: всё вручную в тетради?

**T6** [autonomous_qualification] intent=question_multi_location
> **User**: А для двух точек подойдёт?
> **Bot**: Да, для двух точек подходит тариф Standard за 220 000 ₸ в год. Он включает до трёх точек в одной системе. В рамках этого тарифа вы сможете управлять всеми остатками централизованно без доплат за каждую точку.

**T7** [autonomous_presentation] intent=agreement
> **User**: Да, давайте оформим
> **Bot**: Прекрасно, оформляем тариф Standard для двух точек. Для начала счета на ТОО мне нужно знать ваш ИИН и название компании.

### Сравнение состояний
```
PRE:   autonomous_discovery → autonomous_qualification → autonomous_qualification → autonomous_qualification → autonomous_presentation → autonomous_presentation → autonomous_closing
POST1: autonomous_discovery → autonomous_discovery → autonomous_qualification → autonomous_qualification → autonomous_qualification → autonomous_qualification → autonomous_presentation
```
**⚠️ РАЗЛИЧАЮТСЯ**

---
## T08: Classifier context — 'а скидка?' после обсуждения цен
**Фокус**: classifier_history
**PRE**: PASS | **POST1**: FAIL

### Auto-checks
- `discount_not_discovery`: PRE=✅ POST1=❌ ← CHANGED
- `mentions_discount`: PRE=✅ POST1=✅

### PRE диалог (6 ходов)

**T1** [autonomous_discovery] intent=situation_provided
> **User**: Привет, магазин запчастей для авто, 1 точка
> **Bot**: Отличный формат, автозапчасти — это всегда много артикулов и остатков. Расскажите, с чем сейчас сложнее всего справляться в учёте?

**T2** [autonomous_discovery] intent=question_tariff_lite
> **User**: Сколько стоит Lite?
> **Bot**: Тариф Lite стоит 150 000 тенге в год, это включает одну точку и неограниченную номенклатуру. Для магазина запчастей это отличный старт.

**T3** [autonomous_discovery] intent=question_tariff_standard
> **User**: А Standard?
> **Bot**: Уточните, пожалуйста, что вы имеете в виду под «Standard»:
1) Комплект Standard
2) Тариф Standard
Ответьте номером 1-3 или напишите вариант словами.

**T4** [autonomous_objection_handling] intent=objection_price
> **User**: 220 тысяч в год это немало
> **Bot**: Поняла, тариф Standard стоит 220 000 тенге в год. Он поддерживает до трёх точек и работу с оптовыми ценами, что удобно для роста.

**T5** [autonomous_objection_handling] intent=pricing_details
> **User**: А скидка есть?
> **Bot**: Да, есть. Срок действия акции ограничен по времени. Также для сетей и крупных клиентов доступны корпоративные условия, которые согласуются индивидуально.

**T6** [autonomous_objection_handling] intent=question_installment
> **User**: А рассрочка?
> **Bot**: Да, тарифы и оборудование можно оформить в рассрочку через банки-партнёры. Доступен формат оплаты частями, например, схема 0-0-12 без переплаты. Точные условия зависят от выбранного продукта и банка, а также от вашего формата (ИП/ТОО).

### POST1 диалог (6 ходов)

**T1** [autonomous_discovery] intent=situation_provided
> **User**: Привет, магазин запчастей для авто, 1 точка
> **Bot**: Магазин автозапчастей — отличный формат, у нас есть поддержка поиска по артикулам и учёт остатков. А что сейчас больше всего напрягает в работе с товаром?

**T2** [autonomous_discovery] intent=question_tariff_lite
> **User**: Сколько стоит Lite?
> **Bot**: Тариф Lite стоит 150 000 тенге в год и включает одну торговую точку с неограниченной номенклатурой. Это подходящий вариант для вашего магазина автозапчастей.

**T3** [autonomous_discovery] intent=question_tariff_standard
> **User**: А Standard?
> **Bot**: Уточните, пожалуйста, что вы имеете в виду под «Standard»:
1) Комплект Standard
2) Тариф Standard
Ответьте номером 1-3 или напишите вариант словами.

**T4** [autonomous_discovery] intent=objection_price
> **User**: 220 тысяч в год это немало
> **Bot**: Тариф Standard стоит 220 000 тенге в год и поддерживает до трёх точек с оптовыми ценами. Для одной точки это может быть избыточно, если не нужен расширенный складской учёт.

**T5** [autonomous_qualification] intent=pricing_details
> **User**: А скидка есть?
> **Bot**: Специальные условия доступны при оплате за 2 или 5 лет. Точная величина скидки зависит от согласованного предложения.

**T6** [autonomous_qualification] intent=question_installment
> **User**: А рассрочка?
> **Bot**: Да, и тарифы, и оборудование можно оформить в рассрочку. Для оборудования доступна рассрочка через Kaspi на 12 месяцев без переплаты. Условия рассрочки для тарифов уточняются индивидуально.

### Сравнение состояний
```
PRE:   autonomous_discovery → autonomous_discovery → autonomous_discovery → autonomous_objection_handling → autonomous_objection_handling → autonomous_objection_handling
POST1: autonomous_discovery → autonomous_discovery → autonomous_discovery → autonomous_discovery → autonomous_qualification → autonomous_qualification
```
**⚠️ РАЗЛИЧАЮТСЯ**

---
## T09: Classifier context — 'а на год?' контексто-зависимый вопрос
**Фокус**: classifier_history
**PRE**: FAIL | **POST1**: FAIL

### Auto-checks
- `year_price_given`: PRE=❌ POST1=❌

### PRE диалог (5 ходов)

**T1** [autonomous_discovery] intent=situation_provided
> **User**: Здравствуйте, у меня магазин бытовой техники
> **Bot**: Магазин техники — отлично, Wipon идеально подходит для учёта серийных номеров и гарантий. Расскажите, что сейчас вызывает больше всего трудностей в работе?

**T2** [autonomous_discovery] intent=question_tariff_mini
> **User**: Сколько стоит Mini в месяц?
> **Bot**: Тариф Mini стоит 5 000 тенге в месяц для одной точки с базовой кассой. Сейчас у вас сколько торговых точек работает?

**T3** [autonomous_discovery] intent=cost_inquiry
> **User**: А на год?
> **Bot**: Уточните, пожалуйста, что вы имеете в виду под «Pro»:
1) Комплект Pro
2) Тариф Pro
Ответьте номером 1-3 или напишите вариант словами.

**T4** [autonomous_discovery] intent=question_tariff_lite
> **User**: А Lite?
> **Bot**: Тариф Lite стоит 150 000 тенге в год для одной торговой точки.

**T5** [autonomous_qualification] intent=question_tariff_comparison
> **User**: А чем Lite лучше Mini?
> **Bot**: Lite включает складской учёт, а Mini — только кассу и фискализацию. В Mini нет функций по работе со складом, они начинаются с тарифа Lite.

### POST1 диалог (5 ходов)

**T1** [autonomous_discovery] intent=situation_provided
> **User**: Здравствуйте, у меня магазин бытовой техники
> **Bot**: Магазин техники — отличная ниша, особенно с учётом серийных номеров и гарантий. А что сейчас в работе вызывает больше всего сложностей?

**T2** [autonomous_discovery] intent=question_tariff_mini
> **User**: Сколько стоит Mini в месяц?
> **Bot**: Тариф Mini стоит 5 000 тенге в месяц для одной торговой точки. Там есть онлайн-касса и базовый учёт продаж. Подскажите, сколько у вас сейчас точек, чтобы я могла подобрать оптимальный вариант?

**T3** [autonomous_discovery] intent=cost_inquiry
> **User**: А на год?
> **Bot**: Уточните, пожалуйста, что вы имеете в виду под «Pro»:
1) Комплект Pro
2) Тариф Pro
Ответьте номером 1-3 или напишите вариант словами.

**T4** [autonomous_discovery] intent=question_tariff_lite
> **User**: А Lite?
> **Bot**: Уточните, пожалуйста, что вы имеете в виду под «Pro»:
1) Комплект Pro
2) Тариф Pro
Ответьте номером 1-3 или напишите вариант словами.

**T5** [autonomous_qualification] intent=pricing_comparison
> **User**: А чем Lite лучше Mini?
> **Bot**: Lite стоит 150 000 тенге в год и включает складской учёт, которого нет в Mini. В Mini только касса и продажи за 5 000 тенге в месяц.

### Сравнение состояний
```
PRE:   autonomous_discovery → autonomous_discovery → autonomous_discovery → autonomous_discovery → autonomous_qualification
POST1: autonomous_discovery → autonomous_discovery → autonomous_discovery → autonomous_discovery → autonomous_qualification
```
Одинаковые

---
## T10: Terminal payment_ready — kaspi_phone + iin обязательны
**Фокус**: terminal_requirements
**PRE**: PASS | **POST1**: PASS

### Auto-checks
- `payment_ready`: PRE=✅ POST1=✅
- `reached_final`: PRE=✅ POST1=✅

### PRE диалог (6 ходов)

**T1** [autonomous_discovery] intent=situation_provided
> **User**: Здравствуйте, у меня магазин, хочу подключить Mini
> **Bot**: Отлично, Mini — это хороший старт. А что именно сейчас мешает работать быстрее?

**T2** [autonomous_discovery] intent=situation_provided
> **User**: Да, один магазин, продукты
> **Bot**: Продуктовый магазин — это отличная ниша. Расскажите, как сейчас ведете учёт товаров и кассу?

**T3** [autonomous_closing] intent=agreement
> **User**: Давайте оформим, 5000 в месяц нормально
> **Bot**: Для оплаты через Kaspi нужны ваш ИИН и номер Kaspi. Пожалуйста, укажите их — и мы сразу оформим подписку.

**T4** [autonomous_closing] intent=payment_confirmation
> **User**: Хочу оплатить через Kaspi
> **Bot**: Супер, Kaspi — самый удобный вариант. Для оформления нужен ваш ИИН и номер телефона для оплаты. Напишите их, и я сразу всё оформлю.

**T5** [autonomous_closing] intent=contact_provided
> **User**: Мой Kaspi номер 87017778899
> **Bot**: Спасибо! Мой коллега позвонит вам в ближайшее время и согласует удобное время. Коллега по подключениям перезвонит и всё оформит — удобно?

**T6** [payment_ready] intent=contact_provided
> **User**: ИИН 890623300123
> **Bot**: Спасибо за данные! Коллега позвонит вам для подтверждения оплаты.

### POST1 диалог (6 ходов)

**T1** [autonomous_discovery] intent=situation_provided
> **User**: Здравствуйте, у меня магазин, хочу подключить Mini
> **Bot**: Здорово, что вы определились с форматом. А что сейчас больше всего напрягает в работе с кассой или учётом?

**T2** [autonomous_discovery] intent=situation_provided
> **User**: Да, один магазин, продукты
> **Bot**: Продуктовый магазин — отличная ниша. А что сейчас вызывает трудности в учёте или кассе?

**T3** [autonomous_closing] intent=agreement
> **User**: Давайте оформим, 5000 в месяц нормально
> **Bot**: Отлично, Mini — 5 000 ₸ в месяц, это старт для одной точки. Чтобы оформить доступ, оставьте, пожалуйста, ваш телефон.

**T4** [autonomous_closing] intent=payment_terms
> **User**: Хочу оплатить через Kaspi
> **Bot**: Тарифы и услуги Wipon можно оплатить через Kaspi по номеру или по выставленному счёту для ТОО. Оборудование Wipon можно оформить в рассрочку на 12 месяцев через Kaspi 0-0-12 без переплат.

**T5** [autonomous_closing] intent=contact_provided
> **User**: Мой Kaspi номер 87017778899
> **Bot**: Спасибо! Мой коллега позвонит вам в ближайшее время и согласует удобное время. Коллега по подключениям перезвонит и всё оформит — удобно?

**T6** [payment_ready] intent=contact_provided
> **User**: ИИН 890623300123
> **Bot**: ИИН приняла. А как к вам лучше обращаться?

### Сравнение состояний
```
PRE:   autonomous_discovery → autonomous_discovery → autonomous_closing → autonomous_closing → autonomous_closing → payment_ready
POST1: autonomous_discovery → autonomous_discovery → autonomous_closing → autonomous_closing → autonomous_closing → payment_ready
```
Одинаковые

---
## T11: Terminal video_call_scheduled — contact_info обязателен
**Фокус**: terminal_requirements
**PRE**: PASS | **POST1**: PASS

### Auto-checks
- `asks_contact`: PRE=✅ POST1=✅

### PRE диалог (5 ходов)

**T1** [autonomous_discovery] intent=situation_provided
> **User**: Привет, у нас сеть из 5 магазинов, хотим Pro
> **Bot**: Пять магазинов — отличный масштаб! Wipon Pro идеально подходит для такого количества точек. Расскажите, что сейчас в управлении сетью вызывает больше всего сложностей?

**T2** [autonomous_discovery] intent=need_expressed
> **User**: Да, нам нужна полная автоматизация
> **Bot**: Да, полная автоматизация — это именно то, что мы предлагаем. Все процессы от кассы до склада объединены в одной системе. А какие именно задачи сейчас выполняются вручную и отнимают больше всего времени?

**T3** [autonomous_closing] intent=callback_request
> **User**: Хотим чтобы нам позвонили и всё объяснили подробно
> **Bot**: Отлично, коллега свяжется и всё подробно расскажет по телефону. Оставьте, пожалуйста, ваш номер для обратного звонка.

**T4** [autonomous_closing] intent=callback_request
> **User**: Назначьте звонок на завтра
> **Bot**: Завтра отлично, коллега свяжется и всё согласует. Оставьте, пожалуйста, ваш номер телефона для связи.

**T5** [video_call_scheduled] intent=contact_provided
> **User**: Мой телефон 87021112233
> **Bot**: Спасибо! Мой коллега позвонит вам в ближайшее время и согласует удобное время.

### POST1 диалог (5 ходов)

**T1** [autonomous_discovery] intent=situation_provided
> **User**: Привет, у нас сеть из 5 магазинов, хотим Pro
> **Bot**: Пять магазинов — отличный масштаб для Wipon Pro. Расскажите, какая главная задача сейчас стоит: автоматизация учёта?

**T2** [autonomous_discovery] intent=need_expressed
> **User**: Да, нам нужна полная автоматизация
> **Bot**: Да, Wipon Pro объединяет кассу, склад и аналитику в одной системе без ручных сверок. А как сейчас у вас организован учёт товаров между точками?

**T3** [autonomous_closing] intent=callback_request
> **User**: Хотим чтобы нам позвонили и всё объяснили подробно
> **Bot**: Отлично, коллега всё подробно расскажет и покажет систему вживую. Для связи оставьте, пожалуйста, ваш номер телефона или email.

**T4** [autonomous_closing] intent=callback_request
> **User**: Назначьте звонок на завтра
> **Bot**: Коллега свяжется с вами завтра и согласует точное время звонка. Оставьте, пожалуйста, ваш номер телефона для связи.

**T5** [video_call_scheduled] intent=contact_provided
> **User**: Мой телефон 87021112233
> **Bot**: Спасибо! Мой коллега позвонит вам в ближайшее время и согласует удобное время.

### Сравнение состояний
```
PRE:   autonomous_discovery → autonomous_discovery → autonomous_closing → autonomous_closing → video_call_scheduled
POST1: autonomous_discovery → autonomous_discovery → autonomous_closing → autonomous_closing → video_call_scheduled
```
Одинаковые

---
## T12: Fast-track — demo_request из discovery → closing
**Фокус**: terminal_requirements
**PRE**: PASS | **POST1**: PASS

### Auto-checks
- `no_net_demo`: PRE=✅ POST1=✅
- `reached_closing`: PRE=✅ POST1=✅

### PRE диалог (5 ходов)

**T1** [autonomous_discovery] intent=situation_provided
> **User**: Здравствуйте, у меня цветочный магазин
> **Bot**: Цветочный магазин — это красиво и волнительно! Wipon отлично подходит для таких точек: там есть касса, учёт товаров и быстрое оформление продаж. А что сейчас больше всего напрягает в работе с заказами или остатками?

**T2** [autonomous_closing] intent=demo_request
> **User**: Можно мне демонстрацию программы?
> **Bot**: Конечно, у нас есть бесплатный тестовый период на 7 дней, чтобы вы могли всё проверить в деле. Оставьте, пожалуйста, ваш номер телефона, я передам данные коллеге для настройки доступа.

**T3** [autonomous_closing] intent=situation_provided
> **User**: Ну хорошо, тогда расскажите что есть для одного магазина
> **Bot**: Lite: подходит для одного магазина Для мясного магазина Mini подходит для кассового сценария, а Lite и выше — для склада и аналитики.

**T4** [autonomous_closing] intent=agreement
> **User**: Lite подойдёт, давайте подключим
> **Bot**: Отлично, тариф Lite закрывает все задачи для одной точки. Для оформления оставьте, пожалуйста, ваш телефон или email? Коллега позвонит и оформит подключение — скажите номер?

**T5** [autonomous_closing] intent=contact_provided
> **User**: 87775556677
> **Bot**: Спасибо! Мой коллега позвонит вам в ближайшее время и согласует удобное время. Оставите контакт для связи?

### POST1 диалог (5 ходов)

**T1** [autonomous_discovery] intent=situation_provided
> **User**: Здравствуйте, у меня цветочный магазин
> **Bot**: Цветочный магазин — это прекрасно, Wipon отлично справляется с учётом таких товаров. Расскажите, что сейчас занимает больше всего времени в вашей работе?

**T2** [autonomous_closing] intent=demo_request
> **User**: Можно мне демонстрацию программы?
> **Bot**: Конечно, у нас есть бесплатный тестовый период на 7 дней, чтобы вы могли всё посмотреть. Оставьте, пожалуйста, ваш телефон для связи, чтобы я могла передать данные коллегам для настройки доступа.

**T3** [autonomous_closing] intent=situation_provided
> **User**: Ну хорошо, тогда расскажите что есть для одного магазина
> **Bot**: Готова помочь с подключением. Оставьте телефон или email — коллега позвонит для уточнения деталей.

**T4** [autonomous_closing] intent=agreement
> **User**: Lite подойдёт, давайте подключим
> **Bot**: Отличный выбор, тариф Lite закроет все задачи вашего магазина. Для оформления оставьте, пожалуйста, ваш номер телефона. Коллега позвонит и оформит подключение — скажите номер?

**T5** [autonomous_closing] intent=contact_provided
> **User**: 87775556677
> **Bot**: Спасибо! Мой коллега позвонит вам в ближайшее время и согласует удобное время. Готовы подключить?

### Сравнение состояний
```
PRE:   autonomous_discovery → autonomous_closing → autonomous_closing → autonomous_closing → autonomous_closing
POST1: autonomous_discovery → autonomous_closing → autonomous_closing → autonomous_closing → autonomous_closing
```
Одинаковые

---
## T13: Multi-topic — переключение тем, контекст не теряется
**Фокус**: context_retention
**PRE**: PASS | **POST1**: PASS

### Auto-checks
- `context_retained`: PRE=✅ POST1=✅
- `reaches_closing`: PRE=✅ POST1=✅

### PRE диалог (7 ходов)

**T1** [autonomous_discovery] intent=situation_provided
> **User**: Привет, у меня кафе в Алматы
> **Bot**: Отлично, кафе в Алматы — это прекрасно. Скажите, а что сейчас в работе больше всего напрягает?

**T2** [autonomous_discovery] intent=question_equipment_general
> **User**: Нужна касса, что предложите?
> **Bot**: Для кафе в Wipon есть встроенная касса с фискализацией, которая пробивает чеки и передаёт их в ОФД. Для небольших точек обычно предлагают POS i3, а для высокой нагрузки — POS Premium. Также доступны компактные решения: Wipon Quadro или планшет с Wipon Kassa.

**T3** [autonomous_discovery] intent=question_tariff_standard
> **User**: Сколько стоит Standard?
> **Bot**: Тариф Standard стоит 220 000 тенге в год и включает до трёх торговых точек.

**T4** [autonomous_discovery] intent=question_training
> **User**: А обучение сотрудников входит?
> **Bot**: Расскажите подробнее о вашем бизнесе — это поможет подобрать оптимальное решение.

**T5** [autonomous_qualification] intent=question_ofd_connection
> **User**: А ОФД подключаете?
> **Bot**: Расскажите подробнее о вашем бизнесе — подберу подходящий вариант Wipon.

**T6** [autonomous_qualification] intent=go_back
> **User**: Вернёмся к Standard — там есть учёт остатков?
> **Bot**: Да, в Standard учёт остатков полный: приход, продажа и списание отражаются сразу. Система автоматически считает остатки и синхронизирует их с кассой в реальном времени.

**T7** [video_call_scheduled] intent=contact_provided
> **User**: Хорошо, давайте Standard. Мой номер 87019998877
> **Bot**: Отлично, фиксирую ваш выбор тарифа Standard.

### POST1 диалог (7 ходов)

**T1** [autonomous_discovery] intent=situation_provided
> **User**: Привет, у меня кафе в Алматы
> **Bot**: Кафе в Алматы — отличный формат, Wipon там хорошо работает. Расскажите, что сейчас в учёте?

**T2** [autonomous_discovery] intent=question_equipment_general
> **User**: Нужна касса, что предложите?
> **Bot**: Для кафе в Wipon есть встроенная касса с фискализацией, которая пробивает чеки и передаёт их в ОФД. Для небольших точек обычно предлагают POS i3 или Wipon Quadro, для высокой нагрузки — POS Premium. Также доступны комплекты оборудования: Standard (моноблок, сканер, принтер) для старта и Pro для сети.

**T3** [autonomous_discovery] intent=question_equipment_bundle
> **User**: Сколько стоит Standard?
> **Bot**: Тариф Standard стоит 220 000 тенге в год. Это программное решение для до трёх точек с неограниченным количеством товаров. Если вам нужно оборудование, базовый комплект Standard стоит 168 000 тенге (единоразово) и включает POS i3, сканер и чековый принтер.

**T4** [autonomous_discovery] intent=question_training
> **User**: А обучение сотрудников входит?
> **Bot**: Расскажите подробнее о вашем бизнесе — это поможет подобрать оптимальное решение.

**T5** [autonomous_qualification] intent=question_ofd_connection
> **User**: А ОФД подключаете?
> **Bot**: Да, мы подключаем ОФД под ключ: настраиваем кассу, регистрируем её и проверяем отправку чеков. ОФД работает только вместе с программой Wipon. Это платная услуга — 1 400 тенге в месяц, списание проходит автоматически.

**T6** [autonomous_qualification] intent=go_back
> **User**: Вернёмся к Standard — там есть учёт остатков?
> **Bot**: Да, в тарифе Standard есть полный складской учёт с автоматическим подсчётом остатков по приходу и продажам.

**T7** [video_call_scheduled] intent=contact_provided
> **User**: Хорошо, давайте Standard. Мой номер 87019998877
> **Bot**: Спасибо! Мой коллега позвонит вам в ближайшее время и согласует удобное время.

### Сравнение состояний
```
PRE:   autonomous_discovery → autonomous_discovery → autonomous_discovery → autonomous_discovery → autonomous_qualification → autonomous_qualification → video_call_scheduled
POST1: autonomous_discovery → autonomous_discovery → autonomous_discovery → autonomous_discovery → autonomous_qualification → autonomous_qualification → video_call_scheduled
```
Одинаковые

---
## T14: Long dialog — 10+ ходов, контекст не разваливается
**Фокус**: context_retention
**PRE**: PASS | **POST1**: PASS

### Auto-checks
- `no_stuck_questions`: PRE=✅ POST1=✅
- `state_progression`: PRE=✅ POST1=✅

### PRE диалог (12 ходов)

**T1** [greeting] intent=greeting
> **User**: Здравствуйте
> **Bot**: Меня зовут Айбота, я ваш персональный консультант Wipon. Расскажите, что именно вас интересует?

**T2** [autonomous_discovery] intent=situation_provided
> **User**: У меня магазин строительных материалов, 2 точки в Караганде
> **Bot**: Стройматериалы — отличный выбор. В Wipon удобно работать с разными единицами измерения, например, метрами и штуками. Что сейчас вызывает больше всего трудностей в учёте двух точек?

**T3** [autonomous_discovery] intent=need_expressed
> **User**: Нужна единая система — касса плюс учёт товара
> **Bot**: Wipon объединяет кассу и учёт товаров в одной системе, так что вам не нужно связывать разные программы. Для двух точек в стройматериалах идеально подойдёт тариф Standard с мультискладом. Какой объём товарной номенклатуры у вас сейчас?

**T4** [autonomous_discovery] intent=question_inventory
> **User**: А складской учёт есть?
> **Bot**: Да, складской учёт есть в тарифах Lite и выше. В системе ведётся полный учёт товаров от поступления до продажи, включая контроль остатков и перемещений. Для работы с несколькими точками (мультисклад) доступны тарифы Standard и Pro.

**T5** [autonomous_discovery] intent=question_inventory
> **User**: Между двумя точками перемещение товара поддерживается?
> **Bot**: Да, перемещения между складами поддерживаются в тарифах Standard и Pro, данные синхронизируются с кассой и закупками.

**T6** [autonomous_qualification] intent=question_tariff_standard
> **User**: Сколько стоит Standard?
> **Bot**: Тариф Standard стоит 220 000 тенге в год. Это программный тариф, который включает до трёх торговых точек. Для двух ваших магазинов это оптимальный вариант по цене.

**T7** [autonomous_objection_handling] intent=situation_provided
> **User**: А Pro зачем, если у меня всего 2 точки?
> **Bot**: Pro включает расширенную аналитику, систему лояльности и три оптовые цены, что важно для стройматериалов с разными клиентами.

**T8** [autonomous_objection_handling] intent=question_equipment_general
> **User**: Ок, Standard. А оборудование что нужно?
> **Bot**: Для старта рекомендуем комплект оборудования Standard за 168 000 ₸ (единоразово). В состав входят: сенсорный моноблок Wipon POS i3, ручной сканер штрих-кода с подставкой и чековый принтер. Программа Wipon подключается отдельно по выбранному тарифу (например, Standard за 220 000 ₸/год).

**T9** [autonomous_objection_handling] intent=question_equipment_bundle
> **User**: А сканер штрихкодов входит в комплект?
> **Bot**: Да, ручной сканер штрих-кода с подставкой входит в состав комплекта оборудования Standard. Стоимость комплекта — 168 000 ₸ (единоразово). В него также входят сенсорный моноблок Wipon POS i3 и чековый принтер.

**T10** [autonomous_closing] intent=ready_to_buy
> **User**: Хорошо, давайте Standard тариф + стандартный комплект оборудования
> **Bot**: Уточните, пожалуйста, что вы имеете в виду под «Standard»:
1) Комплект Standard
2) Тариф Standard
Ответьте номером 1-3 или напишите вариант словами.

**T11** [autonomous_closing] intent=agreement
> **User**: Как подключиться?
> **Bot**: Чтобы подобрать оптимальное решение, оставьте телефон или email — мой коллега позвонит и ответит на все вопросы.

**T12** [autonomous_closing] intent=contact_provided
> **User**: 87015553322
> **Bot**: Спасибо! Мой коллега позвонит вам в ближайшее время и согласует удобное время.

### POST1 диалог (12 ходов)

**T1** [greeting] intent=greeting
> **User**: Здравствуйте
> **Bot**: Меня зовут Айбота, я ваш персональный консультант Wipon. Расскажите, что именно вас интересует в нашей системе?

**T2** [autonomous_discovery] intent=situation_provided
> **User**: У меня магазин строительных материалов, 2 точки в Караганде
> **Bot**: Управление: все точки в одной системе Формат: единая система для точки продаж

**T3** [autonomous_discovery] intent=need_expressed
> **User**: Нужна единая система — касса плюс учёт товара
> **Bot**: Для двух точек идеально подойдёт тариф Standard с мультискладским учётом. Сейчас расскажите, как у вас организована приёмка товара на складах?

**T4** [autonomous_discovery] intent=question_inventory
> **User**: А складской учёт есть?
> **Bot**: Да, в Wipon есть полный складской учёт: приёмка, перемещения, ревизия и контроль остатков. Система работает в облаке, поэтому вы видите актуальные данные по обоим складам в реальном времени.

**T5** [autonomous_discovery] intent=question_inventory
> **User**: Между двумя точками перемещение товара поддерживается?
> **Bot**: Да, в тарифах Standard и Pro поддерживается перемещение товаров между складами с полной синхронизацией остатков. Все операции фиксируются с указанием даты, времени и ответственного сотрудника.

**T6** [autonomous_qualification] intent=price_question
> **User**: Сколько стоит Standard?
> **Bot**: Тариф Standard стоит 220 000 тенге в год и включает до трёх торговых точек.

**T7** [autonomous_qualification] intent=situation_provided
> **User**: А Pro зачем, если у меня всего 2 точки?
> **Bot**: Pro даёт расширенную аналитику, систему лояльности и три оптовые цены, что важно при росте сети.

**T8** [autonomous_qualification] intent=question_equipment_general
> **User**: Ок, Standard. А оборудование что нужно?
> **Bot**: Для старта подойдёт комплект оборудования Standard за 168 000 ₸ (единоразово). В него входит сенсорный моноблок, сканер штрих-кодов и принтер чеков. Оборудование оплачивается отдельно от программного тарифа.

**T9** [autonomous_qualification] intent=question_equipment_bundle
> **User**: А сканер штрихкодов входит в комплект?
> **Bot**: Да, в комплект Standard входит ручной сканер штрих-кода с подставкой. Это проводная модель, которая подключается через USB как клавиатура.

**T10** [autonomous_presentation] intent=agreement
> **User**: Хорошо, давайте Standard тариф + стандартный комплект оборудования
> **Bot**: Уточните, пожалуйста, что вы имеете в виду под «Standard»:
1) Комплект Standard
2) Тариф Standard
Ответьте номером 1-3 или напишите вариант словами.

**T11** [autonomous_closing] intent=agreement
> **User**: Как подключиться?
> **Bot**: Чтобы подобрать оптимальное решение, оставьте телефон или email — мой коллега позвонит и ответит на все вопросы.

**T12** [autonomous_closing] intent=contact_provided
> **User**: 87015553322
> **Bot**: Спасибо! Мой коллега позвонит вам в ближайшее время и согласует удобное время.

### Сравнение состояний
```
PRE:   greeting → autonomous_discovery → autonomous_discovery → autonomous_discovery → autonomous_discovery → autonomous_qualification → autonomous_objection_handling → autonomous_objection_handling → autonomous_objection_handling → autonomous_closing → autonomous_closing → autonomous_closing
POST1: greeting → autonomous_discovery → autonomous_discovery → autonomous_discovery → autonomous_discovery → autonomous_qualification → autonomous_qualification → autonomous_qualification → autonomous_qualification → autonomous_presentation → autonomous_closing → autonomous_closing
```
**⚠️ РАЗЛИЧАЮТСЯ**

---
## T15: Казахский + короткие ответы — контекст для classifier
**Фокус**: classifier_history
**PRE**: PASS | **POST1**: PASS

### Auto-checks
- `no_crash`: PRE=✅ POST1=✅

### PRE диалог (7 ходов)

**T1** [autonomous_discovery] intent=situation_provided
> **User**: Сәлеметсіз бе
> **Bot**: Меня зовут Айбота, я консультант Wipon. Чем сейчас занимается ваш бизнес и что хотите автоматизировать в первую очередь?

**T2** [autonomous_discovery] intent=situation_provided
> **User**: Менде дүкен бар, азық-түлік
> **Bot**: Отлично, продуктовый магазин — это всегда высокий поток. Расскажите, что сейчас больше всего отнимает время при работе с покупателями?

**T3** [autonomous_discovery] intent=price_question
> **User**: Бағдарлама қанша тұрады?
> **Bot**: У нас есть тариф Wipon Mini за 5 000 тенге в месяц для одной торговой точки. Это базовый вариант для старта. Оплата производится ежемесячно.

**T4** [autonomous_presentation] intent=agreement
> **User**: Lite жарайды
> **Bot**: Отличный выбор, Lite закрывает все базовые задачи для одной точки. Обучение сотрудников включено в стоимость. Сколько у вас сейчас кассовых аппаратов?

**T5** [autonomous_presentation] intent=agreement
> **User**: Иә
> **Bot**: Цена: 360 000 ₸ (единоразово) Рассрочка Kaspi: 30 000 ₸/мес (0-0-12)

**T6** [autonomous_presentation] intent=info_provided
> **User**: Рахмет, жақсы
> **Bot**: Рада, что информация оказалась полезной. А что именно в текущем учёте отнимает больше всего времени у кассира?

**T7** [video_call_scheduled] intent=contact_provided
> **User**: 87751234567
> **Bot**: Айбота, я вас услышала. Как к вам обращаться? Вы уже выбрали тариф еще хотите рассмотреть другие варианты?

### POST1 диалог (7 ходов)

**T1** [autonomous_discovery] intent=situation_provided
> **User**: Сәлеметсіз бе
> **Bot**: Сәлеметсіз бе! Рада приветствовать вас. Я Айбота, ваш консультант по Wipon.

**T2** [autonomous_discovery] intent=situation_provided
> **User**: Менде дүкен бар, азық-түлік
> **Bot**: Продуктовый магазин — отличный формат. Сейчас как ведёте учёт товаров и кассу?

**T3** [autonomous_discovery] intent=price_question
> **User**: Бағдарлама қанша тұрады?
> **Bot**: Есть тариф Wipon Mini за 5 000 тенге в месяц для одной торговой точки. Это базовый вариант для старта. В тарифе доступно до 5 000 позиций номенклатуры.

**T4** [autonomous_discovery] intent=question_tariff_lite
> **User**: Lite жарайды
> **Bot**: Lite — это 150 000 тенге в год для одной точки с неограниченной номенклатурой. Включает учёт, кассу и ОФД.

**T5** [autonomous_qualification] intent=agreement
> **User**: Иә
> **Bot**: Отлично, Lite закрывает все задачи для одной точки без ограничений по товарам. Обучение включено и проходит прямо при запуске.

**T6** [autonomous_closing] intent=info_provided
> **User**: Рахмет, жақсы
> **Bot**: Для индивидуального расчёта оставьте контакт — коллега позвонит в удобное время.

**T7** [video_call_scheduled] intent=contact_provided
> **User**: 87751234567
> **Bot**: Спасибо! Мой коллега позвонит вам в ближайшее время и согласует удобное время.

### Сравнение состояний
```
PRE:   autonomous_discovery → autonomous_discovery → autonomous_discovery → autonomous_presentation → autonomous_presentation → autonomous_presentation → video_call_scheduled
POST1: autonomous_discovery → autonomous_discovery → autonomous_discovery → autonomous_discovery → autonomous_qualification → autonomous_closing → video_call_scheduled
```
**⚠️ РАЗЛИЧАЮТСЯ**
