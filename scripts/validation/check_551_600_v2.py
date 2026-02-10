#!/usr/bin/env python3
"""Тест retrieval для секций 551-600 с новыми запросами"""
import sys
sys.path.insert(0, 'src')
from src.knowledge.retriever import CascadeRetriever

retriever = CascadeRetriever(use_embeddings=False)

TEST_CASES = [
    # equipment: 551-557, 600
    {'topic': 'equipment_label_printing_551', 'queries': [
        'Как напечатать этикетку в Wipon?',
        'Печать наклеек для товаров',
        'Где в системе печатать этикетки?'
    ]},
    {'topic': 'equipment_label_content_552', 'queries': [
        'Что печатается на наклейке товара?',
        'Какие данные видно на этикетке?',
        'На этикетке есть цена и штрихкод?'
    ]},
    {'topic': 'equipment_label_format_553', 'queries': [
        'Как изменить размер этикетки?',
        'Можно ли поменять шрифт на этикетке?',
        'Какие форматы этикеток поддерживаются?'
    ]},
    {'topic': 'equipment_label_printers_554', 'queries': [
        'Какой принтер нужен для этикеток?',
        'С какими принтерами работает печать этикеток?',
        'Подойдёт ли мой термопринтер для этикеток?'
    ]},
    {'topic': 'equipment_label_bulk_555', 'queries': [
        'Можно ли напечатать сразу 50 этикеток?',
        'Как печатать этикетки партией?',
        'Печать нескольких этикеток одновременно'
    ]},
    {'topic': 'equipment_label_preview_556', 'queries': [
        'Можно ли увидеть этикетку до печати?',
        'Есть превью перед печатью этикетки?',
        'Как проверить этикетку перед отправкой на печать?'
    ]},
    {'topic': 'equipment_label_convenience_557', 'queries': [
        'Чем хороша печать этикеток в Wipon?',
        'Преимущества печати этикеток',
        'Данные на этикетку заполняются сами?'
    ]},
    {'topic': 'equipment_scales_spices_600', 'queries': [
        'Какие весы для специй подойдут?',
        'Нужны весы для мелкого товара на развес',
        'Весы для орехов и трав есть?'
    ]},

    # inventory: 558-564
    {'topic': 'inventory_supplier_database_558', 'queries': [
        'Где хранить данные о поставщиках?',
        'Можно создать карточку поставщика?',
        'Как вести учёт поставщиков?'
    ]},
    {'topic': 'inventory_supplier_select_559', 'queries': [
        'Как указать поставщика при приёмке?',
        'Данные поставщика заполняются автоматом?',
        'Выбор поставщика при закупке товара'
    ]},
    {'topic': 'inventory_supplier_return_560', 'queries': [
        'Как вернуть товар поставщику?',
        'Создать документ возврата поставщику',
        'Возврат брака поставщику'
    ]},
    {'topic': 'inventory_supplier_payment_561', 'queries': [
        'Как отслеживать долги поставщикам?',
        'Какие поставки уже оплачены?',
        'Контроль расчётов с поставщиками'
    ]},
    {'topic': 'inventory_supplier_history_562', 'queries': [
        'История закупок у поставщика',
        'Какие товары покупали у этого поставщика?',
        'Все операции с поставщиком'
    ]},
    {'topic': 'inventory_supplier_export_563', 'queries': [
        'Скачать список поставщиков в Excel',
        'Экспорт данных о закупках',
        'Загрузить базу поставщиков'
    ]},
    {'topic': 'inventory_supplier_benefits_564', 'queries': [
        'Для чего нужен учёт поставщиков?',
        'Плюсы ведения базы поставщиков',
        'Преимущества работы с поставщиками в Wipon'
    ]},

    # mobile: 565-572
    {'topic': 'mobile_app_exists_565', 'queries': [
        'У Wipon есть приложение для телефона?',
        'Можно работать с Wipon на смартфоне?',
        'Мобильная версия Wipon есть?'
    ]},
    {'topic': 'mobile_app_features_566', 'queries': [
        'Какой функционал в мобильном Wipon?',
        'Что умеет приложение Wipon?',
        'Возможности мобильного приложения'
    ]},
    {'topic': 'mobile_app_prices_567', 'queries': [
        'В приложении можно разные цены по точкам?',
        'Разные цены для разных магазинов в мобильном',
        'Цены по локациям в приложении'
    ]},
    {'topic': 'mobile_app_for_ip_568', 'queries': [
        'Приложение подойдёт для индивидуального предпринимателя?',
        'Wipon мобильное для малого бизнеса',
        'Подходит ли для розничной торговли?'
    ]},
    {'topic': 'mobile_app_contractors_569', 'queries': [
        'Клиенты в мобильном приложении',
        'Как работать с поставщиками через телефон?',
        'База контрагентов в приложении'
    ]},
    {'topic': 'mobile_app_analytics_570', 'queries': [
        'Отчёты в мобильном приложении есть?',
        'Статистика продаж на телефоне',
        'Аналитика выручки в приложении'
    ]},
    {'topic': 'mobile_app_history_571', 'queries': [
        'Как посмотреть историю продаж в приложении?',
        'Журнал операций в мобильном',
        'Все транзакции в приложении'
    ]},
    {'topic': 'mobile_app_convenience_572', 'queries': [
        'Почему удобно использовать приложение Wipon?',
        'В чём удобство мобильного Wipon?',
        'Преимущества работы через телефон'
    ]},

    # features: 573-579
    {'topic': 'features_pricelists_what_573', 'queries': [
        'Что такое прайслист в Wipon?',
        'Прайслисты для чего нужны?',
        'Несколько цен на один товар'
    ]},
    {'topic': 'features_pricelists_select_574', 'queries': [
        'Как применить прайслист при продаже?',
        'Выбор ценника на кассе',
        'Как переключить прайслист?'
    ]},
    {'topic': 'features_pricelists_purpose_575', 'queries': [
        'Для чего использовать прайслисты?',
        'Оптовые и розничные цены без дублей',
        'Разные цены для оптовиков'
    ]},
    {'topic': 'features_pricelists_settings_576', 'queries': [
        'Как создать прайслист?',
        'Настройка прайслистов в Wipon',
        'Привязать прайслист к клиенту'
    ]},
    {'topic': 'features_pricelists_tariffs_577', 'queries': [
        'Сколько прайслистов можно создать?',
        'Лимит прайслистов по тарифу',
        'В Pro сколько прайслистов?'
    ]},
    {'topic': 'features_pricelists_location_578', 'queries': [
        'Где найти настройки прайслистов?',
        'В каком разделе прайслисты?',
        'Меню настройки прайслистов'
    ]},
    {'topic': 'features_pricelists_promo_579', 'queries': [
        'Как сделать акционные цены?',
        'Быстро применить скидочный прайслист',
        'Прайслист для распродажи'
    ]},

    # support: 580-587, 598
    {'topic': 'support_wipon_consulting_580', 'queries': [
        'Что за Wipon Consulting?',
        'Бухгалтерия от Wipon',
        'Консалтинговые услуги Wipon'
    ]},
    {'topic': 'support_consulting_services_581', 'queries': [
        'Что делает Wipon Consulting?',
        'Какие услуги по бухучёту?',
        'Ведение бухгалтерии что входит?'
    ]},
    {'topic': 'support_consulting_910_582', 'queries': [
        'Сдадите за меня форму 910?',
        'Помощь с налоговой отчётностью',
        'Кто сдаст НДС отчётность?'
    ]},
    {'topic': 'support_consulting_esf_snt_583', 'queries': [
        'Помогаете с электронными счетами-фактурами?',
        'Оформление СНТ через Wipon',
        'ЭСФ и СНТ кто делает?'
    ]},
    {'topic': 'support_consulting_for_whom_584', 'queries': [
        'Кому подходит бухучёт от Wipon?',
        'Для каких компаний Consulting?',
        'ИП на упрощёнке бухгалтерия'
    ]},
    {'topic': 'support_consulting_benefits_585', 'queries': [
        'Чем хорош Wipon Consulting?',
        'Плюсы бухгалтерии от Wipon',
        'Преимущества Consulting'
    ]},
    {'topic': 'support_consulting_no_accountant_586', 'queries': [
        'Можно ли без своего бухгалтера?',
        'Нужен ли штатный бухгалтер?',
        'Не хочу нанимать бухгалтера'
    ]},
    {'topic': 'support_consulting_reports_587', 'queries': [
        'Какие отчёты даёт Consulting?',
        'Что получу от бухгалтерии Wipon?',
        'Отчёты от Consulting понятные?'
    ]},
    {'topic': 'support_working_hours_598', 'queries': [
        'Во сколько закрываетесь?',
        'Когда можно позвонить менеджеру?',
        'Часы работы поддержки Wipon'
    ]},

    # tis: 588-596
    {'topic': 'tis_wipon_what_588', 'queries': [
        'ТИС от Wipon что это?',
        'Трёхкомпонентная система в Wipon',
        'Что означает ТИС Wipon?'
    ]},
    {'topic': 'tis_benefits_589', 'queries': [
        'Зачем мне ТИС?',
        'Какие выгоды от ТИС?',
        'ТИС повышает лимиты?'
    ]},
    {'topic': 'tis_components_590', 'queries': [
        'Что входит в ТИС?',
        'Из каких частей состоит ТИС?',
        'Три компонента ТИС'
    ]},
    {'topic': 'tis_functions_591', 'queries': [
        'Что умеет ТИС Wipon?',
        'Функционал ТИС',
        'Возможности трёхкомпонентной системы'
    ]},
    {'topic': 'tis_why_connect_592', 'queries': [
        'Почему нужен ТИС?',
        'Стоит ли подключать ТИС?',
        'ТИС поможет избежать НДС?'
    ]},
    {'topic': 'tis_price_593', 'queries': [
        'Цена подключения ТИС?',
        'Сколько платить за ТИС в год?',
        'Стоимость ТИС Wipon'
    ]},
    {'topic': 'tis_official_594', 'queries': [
        'ТИС Wipon законный?',
        'Wipon есть в реестре ТИС?',
        'Официальная ТИС или нет?'
    ]},
    {'topic': 'tis_threshold_duration_595', 'queries': [
        'Когда заканчиваются льготы ТИС?',
        'До какого года пороги ТИС?',
        'Срок повышенных лимитов ТИС'
    ]},
    {'topic': 'tis_to_too_596', 'queries': [
        'ТИС работает для ТОО?',
        'Если стану ТОО что с ТИС?',
        'ТИС только для ИП?'
    ]},

    # pricing: 597
    {'topic': 'pricing_wipon_mini_program_597', 'queries': [
        'Что такое Wipon Mini?',
        'Тариф Mini что включает?',
        'Программа Mini описание'
    ]},

    # regions: 599
    {'topic': 'regions_shymkent_branch_599', 'queries': [
        'Есть офис Wipon в Шымкенте?',
        'Где в Шымкенте найти Wipon?',
        'Адрес Wipon Шымкент'
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
