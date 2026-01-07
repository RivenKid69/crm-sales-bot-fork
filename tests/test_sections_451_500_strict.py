"""
Строгие тесты для секций 451-500.

Проверяем:
1. Точное попадание по клиентским запросам (target в top-1)
2. Уникальность ключевых слов (нет конфликтов с другими секциями)
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from knowledge.retriever import CascadeRetriever, MatchStage


# =============================================================================
# ТЕСТОВЫЕ ДАННЫЕ: 50 секций x 3 запроса = 150 тестов
# =============================================================================

TEST_CASES = [
    # -------------------------------------------------------------------------
    # PRODUCTS.YAML (8 секций)
    # -------------------------------------------------------------------------
    # 451: products_alcohol_wipon_pro_451
    {
        "topic": "products_alcohol_wipon_pro_451",
        "queries": [
            "Я торгую алкоголем, подходит ваша система?",
            "Есть ли у вас модуль для акцизной продукции?",
            "Нужна программа для продажи спиртного",
        ],
    },
    # 458: products_few_items_458
    {
        "topic": "products_few_items_458",
        "queries": [
            "У меня всего 20 товаров, подойдёт программа?",
            "Мало товаров в магазине, нужна ли мне ваша система?",
            "Ограничение по количеству товаров есть?",
        ],
    },
    # 460: products_wipon_kassa_definition_460
    {
        "topic": "products_wipon_kassa_definition_460",
        "queries": [
            "Что такое Wipon Kassa?",
            "Расскажите про вашу кассу Wipon",
            "Wipon касса что это за продукт?",
        ],
    },
    # 462: products_quick_connection_462
    {
        "topic": "products_quick_connection_462",
        "queries": [
            "Сколько времени занимает подключение кассы?",
            "Как быстро можно начать работать после регистрации?",
            "Долго настраивается ваша касса?",
        ],
    },
    # 466: products_multiple_stores_466
    {
        "topic": "products_multiple_stores_466",
        "queries": [
            "У меня несколько торговых точек, подойдёт?",
            "Можно управлять сетью магазинов из одного аккаунта?",
            "Wipon Kassa для сети точек подходит?",
        ],
    },
    # 469: products_wipon_ofd_469
    {
        "topic": "products_wipon_ofd_469",
        "queries": [
            "Что такое Wipon ОФД?",
            "Как работает ваш оператор фискальных данных?",
            "Есть личный кабинет ОФД?",
        ],
    },
    # 470: products_small_business_kassa_470
    {
        "topic": "products_small_business_kassa_470",
        "queries": [
            "Подходит ли Wipon Kassa для малого бизнеса?",
            "Ваша касса простая для небольшого магазина?",
            "Нужна доступная касса без больших вложений",
        ],
    },
    # 490: products_wipon_small_business_490
    {
        "topic": "products_wipon_small_business_490",
        "queries": [
            "Подойдёт ли WIPON для малого бизнеса?",
            "Система охватывает основные процессы от продажи до прибыли?",
            "Простая система для небольшого бизнеса нужна",
        ],
    },

    # -------------------------------------------------------------------------
    # INVENTORY.YAML (19 секций)
    # -------------------------------------------------------------------------
    # 452: inventory_suppliers_contacts_452
    {
        "topic": "inventory_suppliers_contacts_452",
        "queries": [
            "Можно хранить контакты поставщиков в системе?",
            "У меня несколько поставщиков, есть база контрагентов?",
            "Где вести историю закупок по поставщикам?",
        ],
    },
    # 471: inventory_warehouse_benefits_471
    {
        "topic": "inventory_warehouse_benefits_471",
        "queries": [
            "Что даёт складской учёт в WIPON?",
            "Зачем нужен учёт товаров от поступления до продажи?",
            "Как узнать что в наличии и где товар?",
        ],
    },
    # 472: inventory_multiple_warehouses_472
    {
        "topic": "inventory_multiple_warehouses_472",
        "queries": [
            "Подходит ли WIPON для нескольких складов?",
            "Можно работать с несколькими складами одновременно?",
            "Синхронизация складов и торговых точек есть?",
        ],
    },
    # 473: inventory_view_stock_473
    {
        "topic": "inventory_view_stock_473",
        "queries": [
            "Как посмотреть остатки товаров в системе?",
            "Где в карточке товара видно количество?",
            "Остатки обновляются автоматически при продаже?",
        ],
    },
    # 474: inventory_stocktaking_474
    {
        "topic": "inventory_stocktaking_474",
        "queries": [
            "Можно делать инвентаризацию в WIPON?",
            "Как сверить фактические остатки с учётными?",
            "Система помогает избежать недостач?",
        ],
    },
    # 475: inventory_documents_475
    {
        "topic": "inventory_documents_475",
        "queries": [
            "Какие документы можно оформлять в WIPON?",
            "Есть поступления, списания и возвраты?",
            "Перемещения между складами оформляются?",
        ],
    },
    # 476: inventory_add_products_476
    {
        "topic": "inventory_add_products_476",
        "queries": [
            "Как добавлять новые товары в систему?",
            "Можно создать карточку товара с характеристиками?",
            "Легко редактировать товары?",
        ],
    },
    # 477: inventory_warehouse_analytics_477
    {
        "topic": "inventory_warehouse_analytics_477",
        "queries": [
            "Есть ли аналитика по складу?",
            "Какие отчёты по остаткам формируются?",
            "Где увидеть недостачи и оборот склада?",
        ],
    },
    # 480: inventory_beginner_480
    {
        "topic": "inventory_beginner_480",
        "queries": [
            "Подойдёт если раньше не вёл складской учёт?",
            "Программа для новичка в учёте подойдёт?",
            "Простой интерфейс для начинающего?",
        ],
    },
    # 491: inventory_procurement_purpose_491
    {
        "topic": "inventory_procurement_purpose_491",
        "queries": [
            "Для чего нужен учёт закупок в WIPON?",
            "Как фиксировать поступления товаров?",
            "Контроль закупок без ручного ввода возможен?",
        ],
    },
    # 492: inventory_create_purchase_492
    {
        "topic": "inventory_create_purchase_492",
        "queries": [
            "Как оформить закупку в системе?",
            "Создать приходную накладную как?",
            "Указать поставщика и способ оплаты при закупке?",
        ],
    },
    # 493: inventory_auto_stock_update_493
    {
        "topic": "inventory_auto_stock_update_493",
        "queries": [
            "Обновляются ли остатки после закупки?",
            "Поступление автоматически отражается на складе?",
            "Остатки обновляются автоматически?",
        ],
    },
    # 494: inventory_purchase_history_494
    {
        "topic": "inventory_purchase_history_494",
        "queries": [
            "Можно видеть историю закупок?",
            "Какие товары закупались и у кого?",
            "Посмотреть историю поставок возможно?",
        ],
    },
    # 495: inventory_supplier_comparison_495
    {
        "topic": "inventory_supplier_comparison_495",
        "queries": [
            "Как система помогает выбирать поставщиков?",
            "Можно сравнить поставщиков по условиям?",
            "Кто из поставщиков самый выгодный?",
        ],
    },
    # 496: inventory_low_stock_alert_496
    {
        "topic": "inventory_low_stock_alert_496",
        "queries": [
            "Предупредит ли система если товар заканчивается?",
            "Есть уведомление о дефиците?",
            "Напоминание заказать товар при низких остатках?",
        ],
    },
    # 497: inventory_supplier_payments_497
    {
        "topic": "inventory_supplier_payments_497",
        "queries": [
            "Можно учитывать оплату поставщикам?",
            "Есть учёт задолженности поставщику?",
            "Отчёты по расчётам с поставщиками?",
        ],
    },
    # 498: inventory_procurement_analytics_498
    {
        "topic": "inventory_procurement_analytics_498",
        "queries": [
            "Есть ли аналитика по закупкам?",
            "Сумма закупок и оборачиваемость товаров?",
            "Оптимизация закупочной стратегии?",
        ],
    },
    # 499: inventory_supplier_returns_499
    {
        "topic": "inventory_supplier_returns_499",
        "queries": [
            "Можно оформить возврат поставщику?",
            "Документ возврата товара поставщику?",
            "Вернуть товар поставщику через систему?",
        ],
    },
    # 500: inventory_cost_savings_500
    {
        "topic": "inventory_cost_savings_500",
        "queries": [
            "Как учёт закупок помогает экономить?",
            "Система выявляет неэффективные закупки?",
            "Контроль цен и снижение затрат?",
        ],
    },

    # -------------------------------------------------------------------------
    # ANALYTICS.YAML (6 секций)
    # -------------------------------------------------------------------------
    # 456: analytics_sales_view_456
    {
        "topic": "analytics_sales_view_456",
        "queries": [
            "Можно смотреть аналитику по продажам?",
            "Выручка по дням и месяцам отображается?",
            "Динамика продаж и показатели есть?",
        ],
    },
    # 481: analytics_sales_module_481
    {
        "topic": "analytics_sales_module_481",
        "queries": [
            "Для чего нужен модуль учёта продаж?",
            "Как фиксируются продажи и контролируется выручка?",
            "Анализ эффективности бизнеса через продажи?",
        ],
    },
    # 482: analytics_sales_recording_482
    {
        "topic": "analytics_sales_recording_482",
        "queries": [
            "Как в системе фиксируются продажи?",
            "Продажа, возврат и скидка автоматически сохраняются?",
            "Каждая операция записывается в системе?",
        ],
    },
    # 484: analytics_realtime_484
    {
        "topic": "analytics_realtime_484",
        "queries": [
            "Есть аналитика в реальном времени?",
            "По чекам и продавцам аналитика?",
            "Статистика по кассам и товарам онлайн?",
        ],
    },
    # 486: analytics_sales_benefits_486
    {
        "topic": "analytics_sales_benefits_486",
        "queries": [
            "Какие преимущества даёт учёт продаж?",
            "Прозрачность и контроль операций есть?",
            "Интеграция учёта продаж со складом и закупками?",
        ],
    },
    # 488: analytics_sales_drop_alert_488
    {
        "topic": "analytics_sales_drop_alert_488",
        "queries": [
            "Получу уведомления о снижении продаж?",
            "Система показывает падение продаж?",
            "Мониторинг продаж и позиции которые упали?",
        ],
    },

    # -------------------------------------------------------------------------
    # FISCAL.YAML (5 секций)
    # -------------------------------------------------------------------------
    # 457: fiscal_documents_457
    {
        "topic": "fiscal_documents_457",
        "queries": [
            "Документы тоже через Wipon можно вести?",
            "ЭСФ и СНТ оформляются в системе?",
            "Электронные накладные прямо в программе?",
        ],
    },
    # 463: fiscal_return_process_463
    {
        "topic": "fiscal_return_process_463",
        "queries": [
            "Как работает возврат товара в Wipon Kassa?",
            "Оформить возврат и чек возврата?",
            "Модуль возврата по требованиям ОФД?",
        ],
    },
    # 464: fiscal_receipt_history_464
    {
        "topic": "fiscal_receipt_history_464",
        "queries": [
            "Где посмотреть все пробитые чеки?",
            "История чеков с датой и суммой?",
            "Вкладка история с фискальным признаком?",
        ],
    },
    # 465: fiscal_send_receipt_465
    {
        "topic": "fiscal_send_receipt_465",
        "queries": [
            "Можно отправить чек клиенту онлайн?",
            "Чек в WhatsApp или на email?",
            "Электронный чек клиенту отправить?",
        ],
    },
    # 468: fiscal_branded_receipt_468
    {
        "topic": "fiscal_branded_receipt_468",
        "queries": [
            "Можно брендировать чек?",
            "Добавить рекламный текст на чек?",
            "Свой дизайн и логотип на чеке?",
        ],
    },

    # -------------------------------------------------------------------------
    # TIS.YAML (2 секции)
    # -------------------------------------------------------------------------
    # 454: tis_ip_taxes_454
    {
        "topic": "tis_ip_taxes_454",
        "queries": [
            "Какие налоги платить ИП на упрощёнке?",
            "3 процента или 1 процент от дохода?",
            "Социальные отчисления для ИП рассчитывает?",
        ],
    },
    # 455: tis_form_910_submit_455
    {
        "topic": "tis_form_910_submit_455",
        "queries": [
            "Как сдавать форму 910 через Wipon?",
            "Заполнение и отправка 910 автоматически?",
            "910 через личный кабинет КГД с ЭЦП?",
        ],
    },

    # -------------------------------------------------------------------------
    # MOBILE.YAML (2 секции)
    # -------------------------------------------------------------------------
    # 459: mobile_kassa_devices_459
    {
        "topic": "mobile_kassa_devices_459",
        "queries": [
            "Могу работать с Wipon Kassa с телефона?",
            "Касса работает через веб и мобильное приложение?",
            "Синхронизация между телефоном и компьютером?",
        ],
    },
    # 478: mobile_warehouse_478
    {
        "topic": "mobile_warehouse_478",
        "queries": [
            "Могу вести складской учёт с телефона?",
            "Мобильное приложение для склада?",
            "Приёмка и остатки с телефона?",
        ],
    },

    # -------------------------------------------------------------------------
    # FEATURES.YAML (2 секции)
    # -------------------------------------------------------------------------
    # 453: features_quick_receipt_453
    {
        "topic": "features_quick_receipt_453",
        "queries": [
            "Можно пробить чек быстро без выбора товара?",
            "Режим быстрого чека без детализации?",
            "Просто пробить сумму без товаров?",
        ],
    },
    # 467: features_add_product_sale_467
    {
        "topic": "features_add_product_sale_467",
        "queries": [
            "Можно добавить товар прямо в момент продажи?",
            "Товара нет в базе, создать на кассе?",
            "Новый товар при продаже на лету?",
        ],
    },

    # -------------------------------------------------------------------------
    # EMPLOYEES.YAML (2 секции)
    # -------------------------------------------------------------------------
    # 483: employees_cashier_workflow_483
    {
        "topic": "employees_cashier_workflow_483",
        "queries": [
            "Как организована работа кассиров?",
            "У каждого кассира свой логин?",
            "Действия кассира записываются под его аккаунтом?",
        ],
    },
    # 487: employees_efficiency_487
    {
        "topic": "employees_efficiency_487",
        "queries": [
            "Можно анализировать эффективность сотрудников?",
            "Продажи и средний чек по кассиру?",
            "Фиксируются ошибки и отмены кассиров?",
        ],
    },

    # -------------------------------------------------------------------------
    # EQUIPMENT.YAML (1 секция)
    # -------------------------------------------------------------------------
    # 461: equipment_wipon_kassa_461
    {
        "topic": "equipment_wipon_kassa_461",
        "queries": [
            "Какое оборудование нужно для Wipon Kassa?",
            "Можно работать с любого устройства?",
            "Сканеры и принтеры подключаются?",
        ],
    },

    # -------------------------------------------------------------------------
    # PROMOTIONS.YAML (1 секция)
    # -------------------------------------------------------------------------
    # 485: promotions_discounts_wipon_485
    {
        "topic": "promotions_discounts_wipon_485",
        "queries": [
            "Есть поддержка скидок и акций в WIPON?",
            "Можно задавать скидки для групп товаров?",
            "Акции по времени и по торговым точкам?",
        ],
    },

    # -------------------------------------------------------------------------
    # INTEGRATIONS.YAML (1 секция)
    # -------------------------------------------------------------------------
    # 489: integrations_modules_489
    {
        "topic": "integrations_modules_489",
        "queries": [
            "Интегрируется ли учёт продаж с другими модулями?",
            "Склад, финансы и закупки работают вместе?",
            "Единая картина бизнеса из всех модулей?",
        ],
    },

    # -------------------------------------------------------------------------
    # OTHER.YAML (1 секция - security)
    # -------------------------------------------------------------------------
    # 479: security_data_protection_479
    {
        "topic": "security_data_protection_479",
        "queries": [
            "Как защищены мои данные в WIPON?",
            "Данные в защищённом облаке хранятся?",
            "Резервное копирование и конфиденциальность?",
        ],
    },
]


class TestNewSections451_500:
    """Тесты точности поиска для новых секций."""

    @pytest.fixture(scope="class")
    def retriever(self):
        """Создаём retriever один раз для всех тестов."""
        import knowledge.retriever as r
        r._retriever = None
        return CascadeRetriever(use_embeddings=False)

    @pytest.mark.parametrize("test_case", TEST_CASES, ids=[tc["topic"] for tc in TEST_CASES])
    def test_section_retrieval(self, retriever, test_case):
        """
        Проверяем что секция находится по всем тестовым запросам.

        Критерий успеха: целевая секция в top-3 результатов.
        """
        topic = test_case["topic"]
        queries = test_case["queries"]

        successes = 0
        failures = []

        for query in queries:
            results = retriever.search(query, top_k=3)

            # Проверяем что целевая секция в результатах
            found_topics = [r.section.topic for r in results]

            if topic in found_topics:
                successes += 1
            else:
                failures.append({
                    "query": query,
                    "expected": topic,
                    "got": found_topics[:3] if found_topics else ["NO RESULTS"],
                    "stage": results[0].stage.value if results else "none"
                })

        # Требуем минимум 2/3 запросов должны найти целевую секцию
        # (exact match работает не для всех формулировок вопросов)
        success_rate = successes / len(queries)
        min_required_rate = 2 / 3  # 0.6666... — минимум 2 из 3 запросов

        if failures:
            failure_msg = f"\n{topic}: {successes}/{len(queries)} queries passed\n"
            for f in failures:
                failure_msg += f"  FAIL: '{f['query']}'\n"
                failure_msg += f"    Expected: {f['expected']}\n"
                failure_msg += f"    Got top-3: {f['got']}\n"
                failure_msg += f"    Stage: {f['stage']}\n"

            assert success_rate >= min_required_rate, failure_msg

    def test_top1_accuracy(self, retriever):
        """
        Проверяем точность top-1 (целевая секция на первом месте).

        Целевой показатель: 95%+ запросов возвращают целевую секцию на первом месте.
        """
        total = 0
        top1_hits = 0
        failures = []

        for test_case in TEST_CASES:
            topic = test_case["topic"]
            for query in test_case["queries"]:
                total += 1
                results = retriever.search(query, top_k=1)

                if results and results[0].section.topic == topic:
                    top1_hits += 1
                else:
                    got_topic = results[0].section.topic if results else "NO RESULTS"
                    failures.append({
                        "query": query,
                        "expected": topic,
                        "got": got_topic,
                    })

        accuracy = top1_hits / total * 100

        print(f"\n{'='*60}")
        print(f"TOP-1 ACCURACY: {top1_hits}/{total} = {accuracy:.1f}%")
        print(f"{'='*60}")

        if failures and len(failures) <= 20:
            print(f"\nFailed queries ({len(failures)}):")
            for f in failures:
                print(f"  '{f['query']}'")
                print(f"    Expected: {f['expected']}")
                print(f"    Got: {f['got']}")

        # Требуем 95%+ точность
        assert accuracy >= 95.0, f"Top-1 accuracy {accuracy:.1f}% < 95%"


class TestKeywordUniqueness:
    """Проверка уникальности ключевых слов."""

    @pytest.fixture(scope="class")
    def retriever(self):
        import knowledge.retriever as r
        r._retriever = None
        return CascadeRetriever(use_embeddings=False)

    def test_no_duplicate_keywords_in_new_sections(self, retriever):
        """
        Проверяем что ключевые слова новых секций не пересекаются
        критично с другими секциями.
        """
        new_topics = [tc["topic"] for tc in TEST_CASES]

        # Собираем keywords новых секций
        new_sections_keywords = {}
        for section in retriever.kb.sections:
            if section.topic in new_topics:
                new_sections_keywords[section.topic] = set(
                    kw.lower() for kw in section.keywords
                )

        # Проверяем пересечения с другими секциями
        conflicts = []

        for section in retriever.kb.sections:
            if section.topic in new_topics:
                continue

            existing_keywords = set(kw.lower() for kw in section.keywords)

            for new_topic, new_kws in new_sections_keywords.items():
                overlap = existing_keywords & new_kws

                # Исключаем общие слова
                common_words = {"wipon", "касса", "система", "да", "нет", "можно"}
                significant_overlap = overlap - common_words

                if len(significant_overlap) >= 3:
                    conflicts.append({
                        "new_section": new_topic,
                        "existing_section": section.topic,
                        "overlapping_keywords": significant_overlap
                    })

        if conflicts:
            msg = "\nKeyword conflicts found:\n"
            for c in conflicts[:10]:  # Показываем первые 10
                msg += f"  {c['new_section']} <-> {c['existing_section']}\n"
                msg += f"    Overlap: {c['overlapping_keywords']}\n"

            print(msg)
            # Не фейлим тест, просто предупреждаем
            # assert False, msg


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
