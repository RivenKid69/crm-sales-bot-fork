"""
Строгое тестирование секций 401-450.
Требуется ТОЧНОЕ попадание в нужную секцию (в топ-3), иначе тест провален.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from knowledge.retriever import CascadeRetriever, MatchStage

# Тестовые данные: topic -> [разнообразные клиентские запросы]
# Каждый запрос должен ТОЧНО попадать в указанную секцию
TEST_QUERIES = {
    # === SUPPORT SECTIONS (401-410, 414-422) ===
    "support_setup_401": [
        "кто мне настроит wipon?",
        "кто настроит кассу wipon?",
        "помогите настроить wipon пожалуйста",
    ],
    "support_installation_402": [
        "вы сами устанавливаете программу?",
        "установка программы как происходит?",
        "кто установит wipon?",
    ],
    "support_remote_setup_403": [
        "удалённо ставите программу?",
        "выездной монтаж делаете?",
        "монтаж оборудования как?",
    ],
    "support_onsite_visit_404": [
        "вы приезжаете устанавливать?",
        "приедете настроить wipon?",
        "мастер приедет к нам?",
    ],
    "support_different_business_405": [
        "у меня другой вид деятельности",
        "подойдёт для моего бизнеса wipon?",
        "специфика бизнеса у меня особая",
    ],
    "support_refund_request_406": [
        "хочу вернуть деньги за wipon",
        "хочу оформить возврат денег",
        "можете вернуть деньги?",
    ],
    "support_refund_timing_407": [
        "когда вернёте деньги?",
        "сколько ждать возврат денег?",
        "сроки возврата какие?",
    ],
    "support_return_policy_408": [
        "мы передумали покупать",
        "хотим отказаться от заказа",
        "отменить покупку можно?",
    ],
    "support_equipment_return_409": [
        "хочу вернуть оборудование wipon",
        "техника wipon не подошла",
        "вернуть купленное оборудование wipon",
    ],
    "support_program_refund_410": [
        "вернуть оплату за программу wipon",
        "программа не подошла возврат",
        "возврат за программу wipon",
    ],
    "support_payment_confirmed_414": [
        "я уже оплатил wipon",
        "деньги отправил вам",
        "оплата прошла успешно",
    ],
    "support_payment_check_415": [
        "перевёл оплату проверьте",
        "посмотрите мою оплату пожалуйста",
        "проверьте получение оплаты",
    ],
    "support_kaspi_payment_416": [
        "оплатил через kaspi когда свяжетесь?",
        "скинул деньги на kaspi жду",
        "kaspi деньги перевёл вам",
    ],
    "support_equipment_payment_417": [
        "оплатил оборудование wipon",
        "техника wipon оплачена подтвердите",
        "оплата за оборудование wipon прошла",
    ],
    "support_activation_timing_418": [
        "оплатил когда подключите wipon?",
        "внёс оплату когда настроите wipon?",
        "сроки активации wipon?",
    ],
    "support_payment_kz_419": [
        "төлеп қойдым тексеріңіз",
        "ақша жібердім wipon",
        "төлем жасадым тексеріңіз",
    ],
    "support_receipt_kz_420": [
        "чек жібердім қараңызшы",
        "квитанция жібердім тексеріңіз",
        "чек тексеру өтінемін",
    ],
    "support_kaspi_kz_421": [
        "kaspi арқылы төлем жасадым тексеріңіз",
        "каспи арқылы төледім қашан хабарласасыз",
        "kaspi ақша жібердім күтемін",
    ],
    "support_delivery_kz_422": [
        "жабдықты сатып алдым қашан жеткізесіздер?",
        "жабдық жеткізу уақыты қашан?",
        "доставка қашан болады жабдық?",
    ],

    # === REGIONS SECTIONS (412-413) ===
    "regions_offices_412": [
        "офисы wipon в каких городах?",
        "офисы есть в астане и алматы?",
        "в каких городах офисы wipon?",
    ],
    "regions_location_413": [
        "где вы находитесь wipon?",
        "ваш адрес wipon офиса?",
        "wipon офис адрес какой?",
    ],

    # === EQUIPMENT SECTIONS (411) ===
    "equipment_quadro_411": [
        "wipon quadro цена",
        "квадро моноблок wipon",
        "quadro касса сколько?",
    ],

    # === PRODUCTS SECTIONS (423, 425, 443-450) ===
    "products_theft_protection_kz_423": [
        "ұрлықтан қорғау wipon",
        "кассир әрекеттерін бақылау wipon",
        "тауар ұрлығы алдын алу",
    ],
    "products_wipon_overview_kz_425": [
        "wipon туралы айтыңыз",
        "wipon бағдарламасы не істейді?",
        "910 нысаны wipon бар ма?",
    ],
    "products_what_is_wipon_443": [
        "wipon это что такое?",
        "что такое wipon вообще?",
        "это касса или программа wipon?",
    ],
    "products_small_shop_444": [
        "подойдёт для небольшого магазина wipon?",
        "маленькая точка подойдёт wipon?",
        "для малого бизнеса wipon подходит?",
    ],
    "products_easy_to_use_445": [
        "сложно ли разобраться в wipon?",
        "понятный интерфейс у wipon?",
        "без опыта смогу работать в wipon?",
    ],
    "products_equipment_required_446": [
        "нужно ли покупать оборудование для wipon?",
        "wipon работает на телефоне?",
        "можно без оборудования использовать wipon?",
    ],
    "products_advantages_447": [
        "чем wipon лучше других?",
        "преимущества wipon какие?",
        "почему wipon выбрать?",
    ],
    "products_what_is_wipon_448": [
        "первый раз слышу про wipon",
        "wipon вообще что это такое?",
        "система учёта wipon это что?",
    ],
    "products_difficulty_449": [
        "для начинающих подойдёт wipon?",
        "помогите разобраться в программе wipon",
        "не разберусь в wipon помогите",
    ],
    "products_difference_450": [
        "эсф снт wipon есть?",
        "какие отличия wipon от других программ?",
        "wipon отличия преимущества какие?",
    ],

    # === INTEGRATIONS SECTIONS (424) ===
    "integrations_banks_kz_424": [
        "банктермен интеграция бар ма wipon?",
        "pos терминал қосуға болады wipon?",
        "банк интеграциясы wipon қалай?",
    ],

    # === TIS SECTIONS (426) ===
    "tis_overview_kz_426": [
        "тис туралы wipon айтыңыз",
        "тіс wipon қазақша ақпарат",
        "тис жүйесі wipon туралы",
    ],

    # === PRICING SECTIONS (427-442) ===
    "pricing_tariff_mini_427": [
        "тариф mini wipon сколько стоит?",
        "тариф мини 5000 тенге wipon",
        "5000 месяц тариф mini",
    ],
    "pricing_tariff_lite_428": [
        "тариф lite wipon что входит?",
        "тариф лайт 150000 год wipon",
        "150000 год тариф lite",
    ],
    "pricing_tariff_standart_429": [
        "тариф стандарт wipon сколько?",
        "тариф стандарт 220000 тенге год",
        "standart тариф 220000 год",
    ],
    "pricing_tariff_pro_430": [
        "тариф pro wipon цена сколько?",
        "тариф про 500000 wipon",
        "500000 тенге тариф pro wipon",
    ],
    "pricing_wipon_pro_module_431": [
        "wipon pro модуль цена",
        "маркировка модуль wipon цена",
        "модуль акцизной продукции 12000",
    ],
    "pricing_pos_i3_432": [
        "wipon pos i3 цена сколько?",
        "pos i3 wipon 140000",
        "140000 моноблок wipon pos i3",
    ],
    "pricing_screen_433": [
        "второй экран wipon цена",
        "wipon screen стоимость",
        "экран покупателя wipon screen",
    ],
    "pricing_triple_434": [
        "wipon triple цена сколько?",
        "triple стоимость wipon",
        "triple 330000 тенге wipon",
    ],
    "pricing_kit_pro_435": [
        "кассовый комплект pro wipon цена",
        "комплект pro 360000 wipon",
        "360000 комплект pro wipon",
    ],
    "pricing_smart_scales_436": [
        "умные весы wipon цена сколько?",
        "умные весы wipon стоимость",
        "весы 100000 тенге wipon",
    ],
    "pricing_cash_drawer_437": [
        "денежный ящик wipon цена 21000",
        "денежный ящик wipon 21000 тенге",
        "21000 денежный ящик wipon",
    ],
    "pricing_scales_rongta_438": [
        "весы rongta wipon цена",
        "rongta весы 200000 wipon",
        "200000 rongta wipon",
    ],
    "pricing_stand_zebra_439": [
        "подставка zebra wipon цена",
        "zebra wipon 10000",
        "подставка zebra 10000 wipon",
    ],
    "pricing_stand_simple_440": [
        "простая подставка wipon цена",
        "подставка wipon 3000",
        "3000 простая wipon",
    ],
    "pricing_scanner_wp7600l_441": [
        "сканер wp7600l wipon цена",
        "wp7600l 30000 wipon",
        "30000 wp7600l wipon",
    ],
    "pricing_scanner_stationary_442": [
        "стационарный сканер wipon цена 24000",
        "стационарный сканер wipon 24000 тенге",
        "24000 стационарный сканер wipon",
    ],
}


def run_strict_tests():
    """Запустить строгие тесты - требуется ТОЧНОЕ попадание."""
    print("=" * 70)
    print("СТРОГОЕ ТЕСТИРОВАНИЕ СЕКЦИЙ 401-450")
    print("=" * 70)
    print("Требуется ТОЧНОЕ попадание в нужную секцию (в топ-3)")
    print()

    # Инициализация retriever
    import knowledge.retriever as r
    r._retriever = None
    retriever = CascadeRetriever(use_embeddings=False)

    total_tests = 0
    passed_exact = 0
    passed_category = 0
    failed_tests = []

    for expected_topic, queries in TEST_QUERIES.items():
        print(f"\n--- {expected_topic} ---")

        for query in queries:
            total_tests += 1
            results = retriever.search(query, top_k=3)

            if not results:
                failed_tests.append({
                    "expected": expected_topic,
                    "query": query,
                    "error": "NO_RESULTS",
                    "got": None
                })
                print(f"  FAIL: '{query}' -> НЕТ РЕЗУЛЬТАТОВ")
                continue

            found_topics = [r.section.topic for r in results]
            top_result = results[0]

            if expected_topic in found_topics:
                position = found_topics.index(expected_topic) + 1
                score = results[found_topics.index(expected_topic)].score
                stage = results[found_topics.index(expected_topic)].stage.value
                passed_exact += 1
                if position == 1:
                    print(f"  OK: '{query}' -> #1 (score={score:.2f})")
                else:
                    print(f"  OK: '{query}' -> #{position} (score={score:.2f})")
            else:
                # Строгий режим - если не в топ-3, это провал
                top_topic = top_result.section.topic
                top_category = top_result.section.category
                expected_category = expected_topic.split("_")[0]

                if top_category == expected_category:
                    passed_category += 1
                    print(f"  WARN: '{query}' -> {top_topic} (та же категория)")
                else:
                    failed_tests.append({
                        "expected": expected_topic,
                        "query": query,
                        "error": "WRONG_SECTION",
                        "got": found_topics[0]
                    })
                    print(f"  FAIL: '{query}' -> {found_topics[0]}")

    # Итоги
    print("\n" + "=" * 70)
    print("ИТОГИ СТРОГОГО ТЕСТИРОВАНИЯ")
    print("=" * 70)
    print(f"Всего тестов: {total_tests}")
    print(f"Точное попадание: {passed_exact} ({passed_exact/total_tests*100:.1f}%)")
    print(f"Та же категория: {passed_category} ({passed_category/total_tests*100:.1f}%)")
    print(f"Провалено: {len(failed_tests)} ({len(failed_tests)/total_tests*100:.1f}%)")

    accuracy = passed_exact / total_tests * 100
    print(f"\nТОЧНОСТЬ: {accuracy:.1f}%")

    if passed_category > 0:
        print(f"\nЗАПРОСЫ В ТОЙ ЖЕ КАТЕГОРИИ (требуют доработки):")
        # Показать только уникальные секции с проблемами
        problem_sections = set()
        for expected_topic, queries in TEST_QUERIES.items():
            for query in queries:
                results = retriever.search(query, top_k=3)
                if results:
                    found_topics = [r.section.topic for r in results]
                    if expected_topic not in found_topics:
                        top_category = results[0].section.category
                        expected_category = expected_topic.split("_")[0]
                        if top_category == expected_category:
                            problem_sections.add(expected_topic)
        for section in sorted(problem_sections):
            print(f"  - {section}")

    if failed_tests:
        print(f"\nПРОВАЛИВШИЕСЯ ТЕСТЫ:")
        for fail in failed_tests:
            print(f"  • {fail['expected']}: '{fail['query']}' -> {fail['got']}")

    return passed_exact, total_tests, failed_tests


if __name__ == "__main__":
    passed, total, failed = run_strict_tests()

    # Выход с кодом ошибки если точность < 95%
    if passed / total < 0.95:
        sys.exit(1)
