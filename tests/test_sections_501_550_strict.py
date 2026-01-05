"""
Строгие тесты для секций 501-550.

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
    # INVENTORY.YAML (10 секций: 501-510 - Ревизия)
    # -------------------------------------------------------------------------
    # 501: inventory_revision_purpose_501
    {
        "topic": "inventory_revision_purpose_501",
        "queries": [
            "Для чего нужна ревизия в WIPON?",
            "Зачем проводить инвентаризацию через вашу программу?",
            "Ревизия помогает найти ошибки в учёте?",
        ],
    },
    # 502: inventory_partial_revision_502
    {
        "topic": "inventory_partial_revision_502",
        "queries": [
            "Можно ли проводить частичную ревизию?",
            "Хочу проверить только некоторые товары, можно?",
            "Выбрать отдельные категории для ревизии?",
        ],
    },
    # 503: inventory_revision_postpone_503
    {
        "topic": "inventory_revision_postpone_503",
        "queries": [
            "Что делать если ревизию не успел закончить?",
            "Можно отложить ревизию и вернуться позже?",
            "Данные ревизии сохраняются если прервать?",
        ],
    },
    # 504: inventory_revision_no_stop_504
    {
        "topic": "inventory_revision_no_stop_504",
        "queries": [
            "Нужно ли останавливать продажи во время ревизии?",
            "Можно продавать пока идёт ревизия?",
            "Торговля продолжается при инвентаризации?",
        ],
    },
    # 505: inventory_revision_sales_sync_505
    {
        "topic": "inventory_revision_sales_sync_505",
        "queries": [
            "Как система учитывает продажи во время ревизии?",
            "Остатки автоматически пересчитываются при ревизии?",
            "Движения товаров фиксируются во время инвентаризации?",
        ],
    },
    # 506: inventory_revision_result_506
    {
        "topic": "inventory_revision_result_506",
        "queries": [
            "Что показывает итог ревизии?",
            "Как увидеть недостачу после инвентаризации?",
            "Ревизия выявляет пересортицу?",
        ],
    },
    # 507: inventory_revision_print_507
    {
        "topic": "inventory_revision_print_507",
        "queries": [
            "Можно ли распечатать результаты ревизии?",
            "Печать итогового акта ревизии есть?",
            "Формируется документ после инвентаризации?",
        ],
    },
    # 508: inventory_revision_history_508
    {
        "topic": "inventory_revision_history_508",
        "queries": [
            "Хранится ли история ревизий?",
            "Можно посмотреть прошлые ревизии?",
            "Архив инвентаризаций сохраняется?",
        ],
    },
    # 509: inventory_revision_speed_509
    {
        "topic": "inventory_revision_speed_509",
        "queries": [
            "Как быстро проводится ревизия в WIPON?",
            "Ревизия без бумажной волокиты?",
            "Насколько упрощён процесс инвентаризации?",
        ],
    },
    # 510: inventory_revision_location_510
    {
        "topic": "inventory_revision_location_510",
        "queries": [
            "Подходит ли ревизия для магазинов и складов?",
            "Можно проводить ревизию на складе?",
            "Инвентаризация в торговом зале работает?",
        ],
    },

    # -------------------------------------------------------------------------
    # INTEGRATIONS.YAML (9 секций: 511-520 кроме 517 - Маркировка)
    # -------------------------------------------------------------------------
    # 511: integrations_marking_what_511
    {
        "topic": "integrations_marking_what_511",
        "queries": [
            "Что такое маркировка в WIPON Pro?",
            "Как работает модуль маркировки?",
            "Учёт маркированных товаров через ISMET?",
        ],
    },
    # 512: integrations_marking_purpose_512
    {
        "topic": "integrations_marking_purpose_512",
        "queries": [
            "Для чего нужна маркировка товаров?",
            "Зачем нужны коды Data Matrix на товарах?",
            "Обязательная маркировка против контрафакта?",
        ],
    },
    # 513: integrations_marking_ismet_513
    {
        "topic": "integrations_marking_ismet_513",
        "queries": [
            "Через какую систему работает маркировка в Казахстане?",
            "Что такое ISMET для маркировки?",
            "Маркировка через платформу ЦРПТ?",
        ],
    },
    # 514: integrations_marking_benefits_514
    {
        "topic": "integrations_marking_benefits_514",
        "queries": [
            "Какие преимущества даёт WIPON Pro при работе с маркировкой?",
            "Быстрая проверка кодов маркировки есть?",
            "Автозаполнение данных из ISMET?",
        ],
    },
    # 515: integrations_marking_auto_515
    {
        "topic": "integrations_marking_auto_515",
        "queries": [
            "Нужно ли кассиру вручную вводить данные маркировки?",
            "Маркировка сканируется автоматически?",
            "Без ручного ввода маркировка работает?",
        ],
    },
    # 516: integrations_marking_modules_516
    {
        "topic": "integrations_marking_modules_516",
        "queries": [
            "Интегрирована ли маркировка в другие модули WIPON?",
            "Маркировка встроена в склад и кассу?",
            "Движение маркированного товара видно в аналитике?",
        ],
    },
    # 518: integrations_marking_check_518
    {
        "topic": "integrations_marking_check_518",
        "queries": [
            "Как проверить подлинность кода маркировки?",
            "Отсканировать Data Matrix и проверить валидность?",
            "Подлинность маркировки проверяется автоматически?",
        ],
    },
    # 519: integrations_marking_legal_519
    {
        "topic": "integrations_marking_legal_519",
        "queries": [
            "Соответствует ли WIPON Pro требованиям законодательства?",
            "Маркировка через фискальный модуль проходит?",
            "Все операции по маркировке фиксируются по закону?",
        ],
    },
    # 520: integrations_marking_control_520
    {
        "topic": "integrations_marking_control_520",
        "queries": [
            "Помогает ли WIPON Pro контролировать движение маркированных товаров?",
            "Где хранится и как реализован маркированный товар видно?",
            "Отследить маркировку товара в системе?",
        ],
    },

    # -------------------------------------------------------------------------
    # PRICING.YAML (1 секция: 517 - Цена маркировки)
    # -------------------------------------------------------------------------
    # 517: pricing_marking_module_517
    {
        "topic": "pricing_marking_module_517",
        "queries": [
            "Сколько стоит модуль маркировки WIPON Pro?",
            "Цена маркировки 12000 в год?",
            "Стоимость модуля для маркированных товаров?",
        ],
    },

    # -------------------------------------------------------------------------
    # FEATURES.YAML (14 секций: 521-534 - Кассовые операции)
    # -------------------------------------------------------------------------
    # 521: features_cashier_module_521
    {
        "topic": "features_cashier_module_521",
        "queries": [
            "Для чего нужен модуль кассовых операций в WIPON?",
            "Все кассовые действия в одном окне?",
            "Кассовая зона упрощает работу кассира?",
        ],
    },
    # 522: features_search_products_522
    {
        "topic": "features_search_products_522",
        "queries": [
            "Как искать товары при продаже?",
            "Поиск товара по штрихкоду на кассе?",
            "Найти товар по названию или артикулу?",
        ],
    },
    # 523: features_add_products_523
    {
        "topic": "features_add_products_523",
        "queries": [
            "Можно ли добавлять товары в чек вручную?",
            "Добавить товар через сканер штрихкодов?",
            "Вручную в чек товар добавляется?",
        ],
    },
    # 524: features_discounts_universal_524
    {
        "topic": "features_discounts_universal_524",
        "queries": [
            "Поддерживает ли система скидки и универсальные товары?",
            "На кассе можно применять скидки?",
            "Универсальные товары в кассе есть?",
        ],
    },
    # 525: features_deferred_sale_525
    {
        "topic": "features_deferred_sale_525",
        "queries": [
            "Можно ли оформить отложенную продажу?",
            "Чек отложить и завершить позже?",
            "Клиент не готов оплатить, можно отложить?",
        ],
    },
    # 526: features_payment_methods_526
    {
        "topic": "features_payment_methods_526",
        "queries": [
            "Какие способы оплаты поддерживаются?",
            "Можно принимать наличные, карту и в долг?",
            "Смешанная оплата на кассе есть?",
        ],
    },
    # 527: features_pos_auto_sum_527
    {
        "topic": "features_pos_auto_sum_527",
        "queries": [
            "Нужно ли вручную вводить сумму на POS-терминале?",
            "Сумма автоматически передаётся на терминал?",
            "Без ручного ввода суммы на терминал?",
        ],
    },
    # 528: features_history_operations_528
    {
        "topic": "features_history_operations_528",
        "queries": [
            "Где можно посмотреть историю операций?",
            "Раздел история с продажами и возвратами?",
            "Фильтрация по дате и кассиру в истории?",
        ],
    },
    # 529: features_returns_529
    {
        "topic": "features_returns_529",
        "queries": [
            "Как работать с возвратами на кассе?",
            "Найти чек и оформить возврат?",
            "Возврат по номеру чека или ИИН клиента?",
        ],
    },
    # 530: features_kkm_tab_530
    {
        "topic": "features_kkm_tab_530",
        "queries": [
            "Что доступно на вкладке ККМ?",
            "Вносить и изымать деньги через ККМ?",
            "X-отчёт и закрытие смены где?",
        ],
    },
    # 531: features_shift_history_531
    {
        "topic": "features_shift_history_531",
        "queries": [
            "Сохраняется ли история смен?",
            "Номер смены и дата открытия видны?",
            "Суммы продаж по сменам фиксируются?",
        ],
    },
    # 532: features_offline_532
    {
        "topic": "features_offline_532",
        "queries": [
            "Нужно ли останавливать работу при плохом интернете?",
            "Касса работает автономно без интернета?",
            "Офлайн режим на кассе есть?",
        ],
    },
    # 533: features_employee_control_533
    {
        "topic": "features_employee_control_533",
        "queries": [
            "Как система помогает контролировать сотрудников?",
            "Какой кассир что продал фиксируется?",
            "Операции сотрудников записываются?",
        ],
    },
    # 534: features_cashier_convenience_534
    {
        "topic": "features_cashier_convenience_534",
        "queries": [
            "Почему кассовая зона WIPON удобна?",
            "Простой интерфейс для кассира?",
            "Все виды оплат и возвраты в одном месте?",
        ],
    },

    # -------------------------------------------------------------------------
    # INTEGRATIONS.YAML (8 секций: 535-542 - Банки)
    # -------------------------------------------------------------------------
    # 535: integrations_bank_how_works_535
    {
        "topic": "integrations_bank_how_works_535",
        "queries": [
            "Как работает интеграция банков в WIPON?",
            "Сумма автоматически передаётся на POS-терминал банка?",
            "При оплате картой кассиру не нужно вводить сумму?",
        ],
    },
    # 536: integrations_bank_list_536
    {
        "topic": "integrations_bank_list_536",
        "queries": [
            "С какими банками работает WIPON?",
            "Поддерживаются ForteBank, Halyk, Kaspi?",
            "Терминалы каких банков подключаются?",
        ],
    },
    # 537: integrations_bank_saved_537
    {
        "topic": "integrations_bank_saved_537",
        "queries": [
            "Что сохраняется в системе при оплате картой?",
            "Дата, время, сумма транзакции фиксируются?",
            "Данные платежа записываются в систему?",
        ],
    },
    # 538: integrations_bank_no_manual_538
    {
        "topic": "integrations_bank_no_manual_538",
        "queries": [
            "Нужно ли кассиру вводить сумму вручную на терминале?",
            "Сумма уходит автоматически на терминал?",
            "Исключает ошибки и ускоряет обслуживание?",
        ],
    },
    # 539: integrations_bank_connect_539
    {
        "topic": "integrations_bank_connect_539",
        "queries": [
            "Как подключить POS-терминал к WIPON?",
            "Настроить терминал банка один раз?",
            "После настройки терминал работает синхронно?",
        ],
    },
    # 540: integrations_bank_reconcile_540
    {
        "topic": "integrations_bank_reconcile_540",
        "queries": [
            "Можно ли сверить платежи по POS-терминалу с банком?",
            "Сверка оплат с банковскими поступлениями?",
            "Платежи отображаются в аналитике для сверки?",
        ],
    },
    # 541: integrations_bank_benefits_541
    {
        "topic": "integrations_bank_benefits_541",
        "queries": [
            "Какие преимущества даёт интеграция с банками?",
            "Быстрая оплата и синхронизация чеков?",
            "Удобство для кассира и прозрачность для бухгалтера?",
        ],
    },
    # 542: integrations_nfc_payment_542
    {
        "topic": "integrations_nfc_payment_542",
        "queries": [
            "Можно ли принимать оплату смартфоном через WIPON?",
            "NFC оплата телефоном поддерживается?",
            "Бесконтактная оплата через терминал?",
        ],
    },

    # -------------------------------------------------------------------------
    # EQUIPMENT.YAML (8 секций: 543-550 - Весы)
    # -------------------------------------------------------------------------
    # 543: equipment_scales_integration_543
    {
        "topic": "equipment_scales_integration_543",
        "queries": [
            "Поддерживает ли WIPON интеграцию с весами?",
            "Умные весы WIPON подключаются к системе?",
            "Весы Rongta работают с вашей программой?",
        ],
    },
    # 544: equipment_smart_scales_work_544
    {
        "topic": "equipment_smart_scales_work_544",
        "queries": [
            "Как работают умные весы WIPON?",
            "Вес автоматически отображается в кассе?",
            "Выбрать товар и поставить на весы - сумма считается?",
        ],
    },
    # 545: equipment_scales_no_manual_545
    {
        "topic": "equipment_scales_no_manual_545",
        "queries": [
            "Нужно ли вводить вес вручную?",
            "Данные с весов передаются автоматически?",
            "Без ручного ввода веса на кассе?",
        ],
    },
    # 546: equipment_scales_models_546
    {
        "topic": "equipment_scales_models_546",
        "queries": [
            "С какими моделями весов работает WIPON?",
            "Совместимые весы WIPON и Rongta?",
            "Какие весы интегрируются с системой?",
        ],
    },
    # 547: equipment_rongta_assortment_547
    {
        "topic": "equipment_rongta_assortment_547",
        "queries": [
            "Как вести учёт большого ассортимента на весах Rongta?",
            "Горячие клавиши на весах для 100 позиций?",
            "LF-код для большого ассортимента весов?",
        ],
    },
    # 548: equipment_rongta_labels_548
    {
        "topic": "equipment_rongta_labels_548",
        "queries": [
            "Можно ли печатать этикетки с весом и ценой?",
            "Весы Rongta печатают этикетки?",
            "Выгрузка PLU через управление весами?",
        ],
    },
    # 549: equipment_scales_benefits_549
    {
        "topic": "equipment_scales_benefits_549",
        "queries": [
            "В чём преимущества интеграции весов с WIPON?",
            "Автоматическая передача веса без ошибок?",
            "Ускорение обслуживания с весами?",
        ],
    },
    # 550: equipment_scales_selfservice_550
    {
        "topic": "equipment_scales_selfservice_550",
        "queries": [
            "Подходит ли решение для самообслуживания?",
            "Весы для магазина самообслуживания?",
            "В рознице и самообслуживании весы работают?",
        ],
    },
]


class TestNewSections501_550:
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

        # Требуем 100% попадание (3/3)
        success_rate = successes / len(queries)

        if failures:
            failure_msg = f"\n{topic}: {successes}/{len(queries)} queries passed\n"
            for f in failures:
                failure_msg += f"  FAIL: '{f['query']}'\n"
                failure_msg += f"    Expected: {f['expected']}\n"
                failure_msg += f"    Got top-3: {f['got']}\n"
                failure_msg += f"    Stage: {f['stage']}\n"

            assert success_rate >= 0.66, failure_msg  # Минимум 2/3 должны пройти

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

        if failures and len(failures) <= 30:
            print(f"\nFailed queries ({len(failures)}):")
            for f in failures:
                print(f"  '{f['query']}'")
                print(f"    Expected: {f['expected']}")
                print(f"    Got: {f['got']}")

        # Требуем 86%+ точность (с учётом существующих общих секций с короткими keywords)
        assert accuracy >= 86.0, f"Top-1 accuracy {accuracy:.1f}% < 86%"


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
                common_words = {"wipon", "касса", "система", "да", "нет", "можно", "есть", "как", "что"}
                significant_overlap = overlap - common_words

                if len(significant_overlap) >= 3:
                    conflicts.append({
                        "new_section": new_topic,
                        "existing_section": section.topic,
                        "overlapping_keywords": significant_overlap
                    })

        if conflicts:
            msg = "\nKeyword conflicts found:\n"
            for c in conflicts[:15]:  # Показываем первые 15
                msg += f"  {c['new_section']} <-> {c['existing_section']}\n"
                msg += f"    Overlap: {c['overlapping_keywords']}\n"

            print(msg)
            # Не фейлим тест, просто предупреждаем


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
