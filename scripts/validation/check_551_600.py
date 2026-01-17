#!/usr/bin/env python3
"""Тест retrieval для секций 551-600"""
import sys
sys.path.insert(0, 'src')
from knowledge.retriever import CascadeRetriever

retriever = CascadeRetriever(use_embeddings=False)

TEST_CASES = [
    # equipment: 551-557, 600
    {'topic': 'equipment_label_printing_551', 'queries': [
        'Можно ли печатать этикетки в Wipon?',
        'Печать этикеток из карточки товара',
        'Этикетки при приёмке товара распечатать'
    ]},
    {'topic': 'equipment_label_content_552', 'queries': [
        'Что указывается на этикетке товара?',
        'Штрихкод и цена на этикетке есть?',
        'Какая информация на этикетке'
    ]},
    {'topic': 'equipment_label_format_553', 'queries': [
        'Можно настроить размер этикетки?',
        'Формат этикетки 43 на 25 мм',
        'Размер шрифта на этикетке изменить'
    ]},
    {'topic': 'equipment_label_printers_554', 'queries': [
        'Какие принтеры для этикеток поддерживаются?',
        'Термопринтер для этикеток подключить',
        'Совместимые принтеры этикеток'
    ]},
    {'topic': 'equipment_label_bulk_555', 'queries': [
        'Можно распечатать много этикеток сразу?',
        'Массовая печать этикеток на партию',
        'Напечатать 100 этикеток за раз'
    ]},
    {'topic': 'equipment_label_preview_556', 'queries': [
        'Есть предпросмотр этикетки перед печатью?',
        'Как посмотреть как выглядит этикетка',
        'Проверить этикетку перед печатью'
    ]},
    {'topic': 'equipment_label_convenience_557', 'queries': [
        'Почему удобно печатать этикетки в Wipon?',
        'Автоматическое заполнение данных на этикетке',
        'Не нужны ручные шаблоны для этикеток'
    ]},
    {'topic': 'equipment_scales_spices_600', 'queries': [
        'Есть весы для взвешивания специй?',
        'Нужны точные весы для малого веса',
        'Весы для развесных товаров орехи травы'
    ]},

    # inventory: 558-564
    {'topic': 'inventory_supplier_database_558', 'queries': [
        'Можно вести базу поставщиков в Wipon?',
        'Карточки поставщиков с реквизитами',
        'Учёт поставщиков ИИН БИН контакты'
    ]},
    {'topic': 'inventory_supplier_select_559', 'queries': [
        'Как выбрать поставщика при закупке?',
        'Реквизиты поставщика подгружаются автоматически',
        'Поставщик из списка при приёмке'
    ]},
    {'topic': 'inventory_supplier_return_560', 'queries': [
        'Как оформить возврат поставщику?',
        'Документы возврата товара поставщику',
        'История возвратов поставщикам'
    ]},
    {'topic': 'inventory_supplier_payment_561', 'queries': [
        'Как контролировать оплату поставок?',
        'Задолженность перед поставщиком видна?',
        'Оплаченные и неоплаченные поставки'
    ]},
    {'topic': 'inventory_supplier_history_562', 'queries': [
        'Где посмотреть историю работы с поставщиком?',
        'Все операции с поставщиком сохраняются?',
        'У кого закупали и по какой цене'
    ]},
    {'topic': 'inventory_supplier_export_563', 'queries': [
        'Можно выгрузить данные поставщиков в Excel?',
        'Экспорт таблицы закупок',
        'Импорт данных поставщиков'
    ]},
    {'topic': 'inventory_supplier_benefits_564', 'queries': [
        'Какие преимущества учёта поставщиков?',
        'Зачем нужен учёт поставщиков в Wipon?',
        'Контроль задолженности поставщику автоматический'
    ]},

    # mobile: 565-572
    {'topic': 'mobile_app_exists_565', 'queries': [
        'Есть мобильное приложение Wipon?',
        'Можно управлять бизнесом с телефона?',
        'Wipon на телефоне работает?'
    ]},
    {'topic': 'mobile_app_features_566', 'queries': [
        'Что доступно в мобильном приложении?',
        'Функции приложения Wipon',
        'Товарный учёт продажи в приложении'
    ]},
    {'topic': 'mobile_app_prices_567', 'queries': [
        'Разные цены по складам в приложении?',
        'Одна позиция разные цены по локациям',
        'Разделение цен в мобильном'
    ]},
    {'topic': 'mobile_app_for_ip_568', 'queries': [
        'Подходит приложение для ИП?',
        'Мобильное приложение для малого бизнеса',
        'Приложение для торговли'
    ]},
    {'topic': 'mobile_app_contractors_569', 'queries': [
        'Работа с контрагентами через приложение',
        'База клиентов в мобильном приложении',
        'Поиск поставщиков в приложении'
    ]},
    {'topic': 'mobile_app_analytics_570', 'queries': [
        'Есть аналитика в мобильном приложении?',
        'Выручка и прибыль в приложении видна?',
        'Отчёты по сотрудникам в мобильном'
    ]},
    {'topic': 'mobile_app_history_571', 'queries': [
        'История операций в приложении есть?',
        'История продаж и возвратов в мобильном',
        'Фильтрация по периоду в приложении'
    ]},
    {'topic': 'mobile_app_convenience_572', 'queries': [
        'Чем удобно мобильное приложение Wipon?',
        'Экономит время управление с телефона',
        'Прозрачное управление бизнесом с телефона'
    ]},

    # features: 573-579
    {'topic': 'features_pricelists_what_573', 'queries': [
        'Что такое прайслисты в Wipon?',
        'Разные цены на один товар для клиентов',
        'Функция прайслистов'
    ]},
    {'topic': 'features_pricelists_select_574', 'queries': [
        'Как выбрать прайслист при продаже?',
        'Прайслист на кассе выбрать',
        'Цены подставляются из прайслиста'
    ]},
    {'topic': 'features_pricelists_purpose_575', 'queries': [
        'Зачем нужны прайслисты?',
        'Продавать по рознице и опту без дублирования',
        'Разные цены без ручного ввода скидок'
    ]},
    {'topic': 'features_pricelists_settings_576', 'queries': [
        'Как настроить прайслисты?',
        'Связать прайслисты с клиентами',
        'Права доступа к прайслистам'
    ]},
    {'topic': 'features_pricelists_tariffs_577', 'queries': [
        'Сколько прайслистов доступно по тарифам?',
        'В Standart один прайслист, в Pro три',
        'Количество прайслистов по тарифу'
    ]},
    {'topic': 'features_pricelists_location_578', 'queries': [
        'Где настраиваются прайслисты?',
        'Раздел настройка прайслисты в админке',
        'Редактировать прайслисты где'
    ]},
    {'topic': 'features_pricelists_promo_579', 'queries': [
        'Как быстро поменять цены на акцию?',
        'Акционный прайслист выбрать',
        'Цены для распродажи'
    ]},

    # support: 580-587, 598
    {'topic': 'support_wipon_consulting_580', 'queries': [
        'Что такое Wipon Consulting?',
        'Бухгалтерский учёт для ИП и ТОО',
        'Консалтинговая компания Wipon'
    ]},
    {'topic': 'support_consulting_services_581', 'queries': [
        'Какие услуги входят в бухучёт?',
        'Учёт доходов расходов зарплаты',
        'Расчёт налогов и сдача отчётности'
    ]},
    {'topic': 'support_consulting_910_582', 'queries': [
        'Поможете сдать форму 910?',
        'Налоговая отчётность через Consulting',
        'НДС отчётность сдаёте?'
    ]},
    {'topic': 'support_consulting_esf_snt_583', 'queries': [
        'Работаете с ЭСФ и СНТ?',
        'Формирование электронных счетов-фактур',
        'Отправка СНТ через Wipon'
    ]},
    {'topic': 'support_consulting_for_whom_584', 'queries': [
        'Для кого услуга бухучёта?',
        'Бухучёт для ИП на упрощёнке',
        'ТОО с НДС бухгалтерия'
    ]},
    {'topic': 'support_consulting_benefits_585', 'queries': [
        'Какие преимущества Wipon Consulting?',
        'Прозрачные отчёты без скрытых деталей',
        'Учёт по требованиям законодательства'
    ]},
    {'topic': 'support_consulting_no_accountant_586', 'queries': [
        'Нужно ли нанимать штатного бухгалтера?',
        'Можно без бухгалтера обойтись?',
        'Зарплата бухгалтеру не нужна'
    ]},
    {'topic': 'support_consulting_reports_587', 'queries': [
        'Какие отчёты буду получать от Consulting?',
        'Отчёты по выручке расходам прибыли',
        'Понятные отчёты без сложных терминов'
    ]},
    {'topic': 'support_working_hours_598', 'queries': [
        'До скольки работаете?',
        'Время работы менеджеров',
        'График работы Wipon'
    ]},

    # tis: 588-596
    {'topic': 'tis_wipon_what_588', 'queries': [
        'Что такое ТИС Wipon?',
        'Трёхкомпонентная система это что?',
        'ТИС объединяет учёт кассу терминал'
    ]},
    {'topic': 'tis_benefits_589', 'queries': [
        'Какие преимущества ТИС?',
        'Повышенные лимиты дохода с ТИС',
        'Порог НДС увеличивается с ТИС'
    ]},
    {'topic': 'tis_components_590', 'queries': [
        'Из чего состоит ТИС?',
        'Компоненты трёхкомпонентной системы',
        'Учётная система касса POS терминал'
    ]},
    {'topic': 'tis_functions_591', 'queries': [
        'Какие функции у ТИС Wipon?',
        'Что можно делать в ТИС?',
        'Учёт товаров приёмка продажа через ТИС'
    ]},
    {'topic': 'tis_why_connect_592', 'queries': [
        'Зачем подключать ТИС?',
        'Почему стоит использовать ТИС?',
        'Без ТИС упрусь в лимит'
    ]},
    {'topic': 'tis_price_593', 'queries': [
        'Сколько стоит ТИС Wipon?',
        'Цена ТИС 220000 в год',
        'Тариф на ТИС Wipon'
    ]},
    {'topic': 'tis_official_594', 'queries': [
        'ТИС официально признана государством?',
        'Wipon в реестре ТИС?',
        'Соответствует законодательству ТИС'
    ]},
    {'topic': 'tis_threshold_duration_595', 'queries': [
        'До какого года действуют пороги ТИС?',
        'Срок действия повышенных порогов',
        'Пороги ТИС до 2026 2027'
    ]},
    {'topic': 'tis_to_too_596', 'queries': [
        'Можно перейти на ТОО с ТИС?',
        'ТИС при переходе на ТОО',
        'ТИС только для ИП?'
    ]},

    # pricing: 597
    {'topic': 'pricing_wipon_mini_program_597', 'queries': [
        'Что такое программа Wipon Mini?',
        'Что входит в тариф Mini?',
        'Базовый учёт в Wipon Mini'
    ]},

    # regions: 599
    {'topic': 'regions_shymkent_branch_599', 'queries': [
        'Есть филиал в Шымкенте?',
        'Офис Wipon в Шымкенте',
        'Можно приехать в Шымкенте посмотреть'
    ]},
]

failures = []
success = 0
total = 0

for tc in TEST_CASES:
    for q in tc['queries']:
        total += 1
        results = retriever.search(q, top_k=3)
        got = results[0].section.topic if results else 'NO RESULTS'
        if got == tc['topic']:
            success += 1
        else:
            # Проверим в top-3
            top3_topics = [r.section.topic for r in results[:3]] if results else []
            if tc['topic'] in top3_topics:
                failures.append((tc['topic'], q, got, f"in top3 at {top3_topics.index(tc['topic'])+1}"))
            else:
                failures.append((tc['topic'], q, got, "NOT in top3"))

accuracy = success / total * 100
print(f'Accuracy: {success}/{total} = {accuracy:.1f}%')
print(f'Failures: {len(failures)}')
print()

for expected, query, got, note in failures:
    print(f'Expected: {expected}')
    print(f'  Query: {query}')
    print(f'  Got: {got} ({note})')
    print()
