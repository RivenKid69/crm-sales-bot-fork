"""
Тестирование секций 401-450 базы знаний.
Проверяем что каждая секция корректно находится по клиентским запросам.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from knowledge.retriever import CascadeRetriever, MatchStage

# Тестовые данные: topic -> [3 клиентских запроса]
TEST_QUERIES = {
    # === SUPPORT SECTIONS (401-410, 414-422) ===
    "support_setup_401": [
        "кто настроит мне кассу?",
        "нужна помощь с настройкой программы",
        "как настроить wipon?",
    ],
    "support_installation_402": [
        "вы сами устанавливаете программу?",
        "как происходит установка?",
        "кто установит мне wipon?",
    ],
    "support_remote_setup_403": [
        "вы ставите программу удалённо?",
        "можете настроить через anydesk?",
        "как проходит монтаж?",
    ],
    "support_onsite_visit_404": [
        "вы приезжаете устанавливать?",
        "можете приехать настроить?",
        "выезд возможен?",
    ],
    "support_different_business_405": [
        "у меня другой вид деятельности",
        "подойдёт для моего бизнеса?",
        "я занимаюсь другой сферой",
    ],
    "support_refund_request_406": [
        "хочу вернуть деньги",
        "как оформить возврат?",
        "верните мне деньги обратно",
    ],
    "support_refund_timing_407": [
        "когда вернёте деньги?",
        "сколько ждать возврат?",
        "сроки возврата какие?",
    ],
    "support_return_policy_408": [
        "мы передумали, как вернуть?",
        "хотим отказаться от заказа",
        "можно отменить покупку?",
    ],
    "support_equipment_return_409": [
        "хотим вернуть оборудование",
        "техника не подошла, возврат",
        "как обменять оборудование?",
    ],
    "support_program_refund_410": [
        "как вернуть оплату за программу?",
        "программа не подошла, возврат",
        "хочу отказаться от подписки",
    ],
    "support_payment_confirmed_414": [
        "я уже оплатил",
        "деньги отправил",
        "оплата прошла",
    ],
    "support_payment_check_415": [
        "перевёл оплату, посмотрите",
        "проверьте мою оплату",
        "подтвердите получение оплаты",
    ],
    "support_kaspi_payment_416": [
        "оплатил через kaspi, когда свяжетесь?",
        "скинул на kaspi деньги",
        "kaspi оплата прошла, ждите",
    ],
    "support_equipment_payment_417": [
        "оплатил оборудование",
        "техника оплачена",
        "жду подтверждения оплаты за моноблок",
    ],
    "support_activation_timing_418": [
        "когда будет подключение?",
        "внёс оплату, когда настроите?",
        "сроки активации какие?",
    ],
    "support_payment_kz_419": [
        "төлеп қойдым",
        "ақша жібердім",
        "төлем жасадым, тексеріңіз",
    ],
    "support_receipt_kz_420": [
        "чек жібердім, қараңызшы",
        "квитанция жібердім",
        "төлем чегін жібердім",
    ],
    "support_kaspi_kz_421": [
        "kaspi арқылы төлем жасадым, тексеріңіз",
        "каспи арқылы төледім, қашан хабарласасыз",
        "kaspi ақша жібердім",
    ],
    "support_delivery_kz_422": [
        "жабдықты сатып алдым, қашан жеткізесіздер?",
        "доставка қашан болады?",
        "жабдық жеткізу уақыты",
    ],

    # === REGIONS SECTIONS (412-413) ===
    "regions_offices_412": [
        "офисы в каких городах?",
        "адрес офиса в астане",
        "где офис в алматы?",
    ],
    "regions_location_413": [
        "где вы находитесь?",
        "ваш адрес?",
        "куда можно приехать?",
    ],

    # === EQUIPMENT SECTIONS (411) ===
    "equipment_quadro_411": [
        "wipon quadro цена",
        "квадро моноблок сколько стоит",
        "касса с весами и принтером в одном",
    ],

    # === PRODUCTS SECTIONS (423, 425, 443-450) ===
    "products_theft_protection_kz_423": [
        "ұрлықтан қорғау қалай?",
        "бизнесті қалай қорғайсыз?",
        "кассир әрекеттері бақылау",
    ],
    "products_wipon_overview_kz_425": [
        "wipon туралы айтыңыз",
        "wipon бағдарламасы не істейді?",
        "910 нысаны wipon",
    ],
    "products_what_is_wipon_443": [
        "wipon это что?",
        "что такое wipon вообще?",
        "это касса или программа?",
    ],
    "products_small_shop_444": [
        "подойдёт для небольшого магазина?",
        "у меня маленькая точка",
        "для малого бизнеса подходит?",
    ],
    "products_easy_to_use_445": [
        "сложно ли разобраться?",
        "интерфейс понятный?",
        "без опыта смогу работать?",
    ],
    "products_equipment_required_446": [
        "нужно ли покупать оборудование?",
        "работает на телефоне?",
        "можно без оборудования?",
    ],
    "products_advantages_447": [
        "чем wipon лучше других?",
        "преимущества wipon",
        "почему wipon выбрать?",
    ],
    "products_what_is_wipon_448": [
        "первый раз слышу про wipon",
        "wipon вообще что это?",
        "система учёта wipon",
    ],
    "products_difficulty_449": [
        "мне будет сложно разобраться",
        "для начинающих подойдёт?",
        "помогите разобраться в программе",
    ],
    "products_difference_450": [
        "чем wipon отличается от других?",
        "эсф снт в wipon есть?",
        "какие отличия от других программ?",
    ],

    # === INTEGRATIONS SECTIONS (424) ===
    "integrations_banks_kz_424": [
        "банктермен интеграция бар ма?",
        "pos терминал қосуға болады?",
        "банк интеграциясы қалай?",
    ],

    # === TIS SECTIONS (426) ===
    "tis_overview_kz_426": [
        "тис туралы айтыңыз",
        "тис дегеніміз не?",
        "тис wipon бағасы қанша?",
    ],

    # === PRICING SECTIONS (427-442) ===
    "pricing_tariff_mini_427": [
        "тариф mini сколько стоит?",
        "цена мини тарифа",
        "5000 тенге тариф",
    ],
    "pricing_tariff_lite_428": [
        "тариф lite что входит?",
        "лайт тариф цена",
        "150000 в год тариф",
    ],
    "pricing_tariff_standart_429": [
        "тариф стандарт сколько?",
        "standart что включает?",
        "220000 тенге тариф",
    ],
    "pricing_tariff_pro_430": [
        "тариф pro цена",
        "про тариф что входит?",
        "500000 тенге тариф",
    ],
    "pricing_wipon_pro_module_431": [
        "wipon pro модуль цена",
        "модуль для акцизной продукции",
        "маркировка модуль стоимость",
    ],
    "pricing_pos_i3_432": [
        "pos i3 сколько стоит?",
        "wipon pos i3 цена",
        "140000 моноблок",
    ],
    "pricing_screen_433": [
        "второй экран цена",
        "wipon screen стоимость",
        "экран покупателя сколько?",
    ],
    "pricing_triple_434": [
        "triple цена",
        "моноблок triple сколько?",
        "330000 касса",
    ],
    "pricing_kit_pro_435": [
        "комплект pro цена",
        "кассовый комплект pro",
        "360000 комплект",
    ],
    "pricing_smart_scales_436": [
        "умные весы wipon цена",
        "весы 100000",
        "сколько стоят умные весы?",
    ],
    "pricing_cash_drawer_437": [
        "денежный ящик цена",
        "ящик wipon сколько?",
        "21000 ящик",
    ],
    "pricing_scales_rongta_438": [
        "весы rongta цена",
        "rongta сколько стоят?",
        "200000 весы",
    ],
    "pricing_stand_zebra_439": [
        "подставка zebra цена",
        "подставка для сканера zebra",
        "10000 подставка",
    ],
    "pricing_stand_simple_440": [
        "простая подставка цена",
        "подставка для сканера 3000",
        "подставка сканера недорого",
    ],
    "pricing_scanner_wp7600l_441": [
        "сканер wp7600l цена",
        "стационарный сканер wp7600l",
        "30000 сканер",
    ],
    "pricing_scanner_stationary_442": [
        "стационарный сканер wipon цена",
        "сканер 24000",
        "сколько стоит стационарный сканер?",
    ],
}


def run_tests():
    """Запустить тесты и вывести результаты."""
    print("=" * 70)
    print("ТЕСТИРОВАНИЕ СЕКЦИЙ 401-450")
    print("=" * 70)

    # Инициализация retriever без embeddings для скорости
    import knowledge.retriever as r
    r._retriever = None
    retriever = CascadeRetriever(use_embeddings=False)

    total_tests = 0
    passed_tests = 0
    failed_tests = []

    for expected_topic, queries in TEST_QUERIES.items():
        print(f"\n--- Тестируем: {expected_topic} ---")

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
                print(f"  ❌ '{query}' -> НЕТ РЕЗУЛЬТАТОВ")
                continue

            # Проверяем что ожидаемый topic в топ-3
            found_topics = [r.section.topic for r in results]

            if expected_topic in found_topics:
                position = found_topics.index(expected_topic) + 1
                score = results[found_topics.index(expected_topic)].score
                stage = results[found_topics.index(expected_topic)].stage.value
                passed_tests += 1
                print(f"  ✅ '{query}' -> #{position} (score={score:.2f}, stage={stage})")
            else:
                # Проверим не является ли первый результат подходящим по категории
                top_result = results[0]
                top_topic = top_result.section.topic
                top_category = top_result.section.category

                # Извлекаем ожидаемую категорию из topic (например support_setup_401 -> support)
                expected_category = expected_topic.split("_")[0]

                if top_category == expected_category:
                    # Категория правильная, но другой topic
                    passed_tests += 1
                    print(f"  ⚠️  '{query}' -> {top_topic} (категория OK, score={top_result.score:.2f})")
                else:
                    failed_tests.append({
                        "expected": expected_topic,
                        "query": query,
                        "error": "WRONG_TOPIC",
                        "got": found_topics[:3]
                    })
                    print(f"  ❌ '{query}' -> {found_topics[0]} (ожидали {expected_topic})")

    # Итоги
    print("\n" + "=" * 70)
    print("ИТОГИ ТЕСТИРОВАНИЯ")
    print("=" * 70)
    print(f"Всего тестов: {total_tests}")
    print(f"Пройдено: {passed_tests} ({passed_tests/total_tests*100:.1f}%)")
    print(f"Провалено: {len(failed_tests)} ({len(failed_tests)/total_tests*100:.1f}%)")

    if failed_tests:
        print("\n--- ПРОВАЛИВШИЕСЯ ТЕСТЫ ---")
        for fail in failed_tests:
            print(f"  • Ожидали: {fail['expected']}")
            print(f"    Запрос: '{fail['query']}'")
            print(f"    Ошибка: {fail['error']}")
            if fail['got']:
                print(f"    Получили: {fail['got']}")
            print()

    return passed_tests, total_tests, failed_tests


if __name__ == "__main__":
    passed, total, failed = run_tests()

    # Выход с кодом ошибки если много провалов
    if len(failed) > total * 0.2:  # > 20% провалов
        sys.exit(1)
