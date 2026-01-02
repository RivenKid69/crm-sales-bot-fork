#!/usr/bin/env python3
"""
Стресс-тест базы знаний Wipon.

Тестирует retriever с разнообразными формулировками запросов,
как от реальных пользователей: разговорные, с опечатками,
на разных языках, с эмоциями и т.д.

Запуск:
    python scripts/stress_test_knowledge.py
    python scripts/stress_test_knowledge.py --verbose
    python scripts/stress_test_knowledge.py --category pricing
"""

import sys
import os
import argparse
from typing import List, Dict, Tuple
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.knowledge.retriever import KnowledgeRetriever
from src.knowledge.data import WIPON_KNOWLEDGE


@dataclass
class TestCase:
    """Тестовый кейс"""
    query: str                    # Запрос пользователя
    expected_topics: List[str]    # Ожидаемые topic_id (хотя бы один должен найтись)
    category: str                 # Категория теста для фильтрации
    description: str = ""         # Описание теста


# =============================================================================
# ТЕСТОВЫЕ КЕЙСЫ
# =============================================================================

TEST_CASES = [
    # =========================================================================
    # ТАРИФЫ И ЦЕНЫ
    # =========================================================================

    # Прямые вопросы
    TestCase("Сколько стоит?", ["tariffs", "tariffs_detailed"], "pricing", "Прямой вопрос о цене"),
    TestCase("Какая цена?", ["tariffs", "tariffs_detailed"], "pricing", "Прямой вопрос"),
    TestCase("Почём?", ["tariffs", "tariffs_detailed"], "pricing", "Разговорный"),
    TestCase("Прайс есть?", ["tariffs", "tariffs_detailed"], "pricing", "Разговорный"),
    TestCase("Скинь прайс", ["tariffs", "tariffs_detailed"], "pricing", "Молодёжный сленг"),

    # С опечатками
    TestCase("скока стоит", ["tariffs", "tariffs_detailed"], "pricing", "С опечаткой"),
    TestCase("прас лист", ["tariffs", "tariffs_detailed"], "pricing", "С опечаткой"),
    TestCase("тарифы какие", ["tariffs", "tariffs_detailed"], "pricing", "Инверсия"),

    # Развёрнутые
    TestCase("Расскажите о ваших тарифах подробнее", ["tariffs", "tariffs_detailed"], "pricing", "Вежливый"),
    TestCase("Хочу узнать стоимость вашей программы", ["tariffs", "tariffs_detailed"], "pricing", "Вежливый"),
    TestCase("Интересует ценовая политика", ["tariffs", "tariffs_detailed"], "pricing", "Формальный"),

    # Конкретные тарифы
    TestCase("Что входит в тариф Mini?", ["tariffs_detailed"], "pricing", "Конкретный тариф"),
    TestCase("Расскажи про Lite", ["tariffs_detailed"], "pricing", "Конкретный тариф"),
    TestCase("Чем отличается Standard от Pro?", ["tariffs_detailed"], "pricing", "Сравнение"),
    TestCase("мини или лайт что лучше", ["tariffs_detailed"], "pricing", "Разговорный"),

    # Wipon Pro цены
    TestCase("Сколько стоит проверка алкоголя?", ["wipon_pro_pricing", "wipon_pro"], "pricing", "Wipon Pro"),
    TestCase("Цена на укм проверку", ["wipon_pro_pricing", "wipon_pro"], "pricing", "Wipon Pro"),

    # Бесплатное
    TestCase("Есть бесплатная версия?", ["free"], "pricing", "Бесплатное"),
    TestCase("Можно попробовать бесплатно?", ["free"], "pricing", "Пробный период"),
    TestCase("триал есть?", ["free"], "pricing", "Английский термин"),
    TestCase("демо версия", ["free"], "pricing", "Демо"),

    # =========================================================================
    # ПРОДУКТЫ
    # =========================================================================

    # Касса
    TestCase("Расскажите про кассу", ["wipon_kassa"], "products", "Прямой вопрос"),
    TestCase("Как работает онлайн касса?", ["wipon_kassa"], "products", "Как работает"),
    TestCase("нужен ккм", ["wipon_kassa"], "products", "Сокращение"),
    TestCase("чеки пробивать как", ["wipon_kassa"], "products", "Разговорный"),
    TestCase("фискальный аппарат", ["wipon_kassa"], "products", "Термин"),
    TestCase("офд подключение", ["wipon_kassa"], "products", "ОФД"),

    # Алкоголь/Pro
    TestCase("Как проверять алкоголь?", ["wipon_pro"], "products", "Прямой вопрос"),
    TestCase("укм сканер", ["wipon_pro"], "products", "УКМ"),
    TestCase("акцизные марки", ["wipon_pro"], "products", "Акциз"),
    TestCase("проверка подлинности алкоголя", ["wipon_pro"], "products", "Подлинность"),
    TestCase("продаём спиртное, что нужно?", ["wipon_pro"], "products", "Разговорный"),
    TestCase("штрафы за контрафакт", ["wipon_pro"], "products", "Штрафы"),

    # Desktop
    TestCase("Программа для компьютера есть?", ["wipon_desktop"], "products", "ПК"),
    TestCase("нужна программа на винду", ["wipon_desktop"], "products", "Разговорный"),
    TestCase("учёт товаров на пк", ["wipon_desktop"], "products", "Учёт"),

    # ТИС
    TestCase("Что такое ТИС?", ["wipon_tis"], "products", "Вопрос о ТИС"),
    TestCase("упрощёнка форма 910", ["wipon_tis"], "products", "Форма 910"),
    TestCase("снт выписать", ["wipon_tis"], "products", "СНТ"),
    TestCase("электронные счета фактуры", ["wipon_tis"], "products", "ЭСФ"),

    # Мобильное приложение
    TestCase("Есть приложение на телефон?", ["mobile_app"], "products", "Мобильное"),
    TestCase("скачать на айфон", ["mobile_app"], "products", "iOS"),
    TestCase("андроид приложение", ["mobile_app"], "products", "Android"),

    # Лояльность/Cashback
    TestCase("Программа лояльности для клиентов", ["wipon_cashback"], "products", "Лояльность"),
    TestCase("бонусы начислять как", ["wipon_cashback"], "products", "Бонусы"),
    TestCase("кэшбэк система", ["wipon_cashback"], "products", "Кэшбэк"),

    # Общий обзор
    TestCase("Что вы предлагаете?", ["overview"], "products", "Общий вопрос"),
    TestCase("какие продукты есть", ["overview"], "products", "Общий вопрос"),
    TestCase("что умеет ваша система", ["overview"], "products", "Функции"),

    # =========================================================================
    # ФУНКЦИИ
    # =========================================================================

    # Склад
    TestCase("Как вести учёт товаров?", ["inventory"], "features", "Учёт"),
    TestCase("складской учёт", ["inventory"], "features", "Склад"),
    TestCase("остатки на складе", ["inventory"], "features", "Остатки"),
    TestCase("ревизия как делать", ["inventory"], "features", "Ревизия"),
    TestCase("инвентаризация", ["inventory"], "features", "Инвентаризация"),

    # Отчёты
    TestCase("Какие отчёты есть?", ["reports"], "features", "Отчёты"),
    TestCase("аналитика продаж", ["reports"], "features", "Аналитика"),
    TestCase("abc анализ", ["reports"], "features", "ABC"),
    TestCase("статистика выручки", ["reports"], "features", "Выручка"),

    # Сотрудники
    TestCase("Учёт сотрудников есть?", ["employees"], "features", "Сотрудники"),
    TestCase("зарплату считать", ["employees"], "features", "Зарплата"),
    TestCase("кадровый учёт", ["employees"], "features", "Кадры"),

    # =========================================================================
    # ИНТЕГРАЦИИ
    # =========================================================================

    # Kaspi
    TestCase("Работаете с Kaspi?", ["marketplaces"], "integrations", "Kaspi"),
    TestCase("каспи магазин интеграция", ["marketplaces"], "integrations", "Kaspi"),
    TestCase("синхронизация с каспи", ["marketplaces"], "integrations", "Kaspi"),
    TestCase("kaspi.kz", ["marketplaces"], "integrations", "Kaspi URL"),

    # Halyk
    TestCase("Халык маркет поддерживаете?", ["marketplaces"], "integrations", "Halyk"),

    # Банки/терминалы
    TestCase("Подключить POS терминал", ["payments"], "integrations", "POS"),
    TestCase("эквайринг", ["payments"], "integrations", "Эквайринг"),
    TestCase("оплата картой", ["payments"], "integrations", "Карта"),

    # Маркировка
    TestCase("Маркировка товаров", ["marking"], "integrations", "Маркировка"),
    TestCase("штрихкоды сканировать", ["marking"], "integrations", "Штрихкоды"),

    # 1С
    TestCase("Выгрузка в 1С", ["1c"], "integrations", "1С"),
    TestCase("интеграция с бухгалтерией", ["1c"], "integrations", "1С"),
    TestCase("синхронизация с 1с", ["1c"], "integrations", "1С"),

    # =========================================================================
    # ОБОРУДОВАНИЕ
    # =========================================================================

    TestCase("Какой сканер купить?", ["hardware"], "equipment", "Сканер"),
    TestCase("принтер чеков подойдёт?", ["hardware"], "equipment", "Принтер"),
    TestCase("весы подключить", ["hardware"], "equipment", "Весы"),
    TestCase("тсд совместимость", ["hardware"], "equipment", "ТСД"),
    TestCase("какое оборудование нужно", ["hardware"], "equipment", "Общий вопрос"),
    TestCase("honeywell сканер", ["hardware"], "equipment", "Бренд"),
    TestCase("термопринтер 80мм", ["hardware"], "equipment", "Конкретное оборудование"),

    # =========================================================================
    # РЕГИОНЫ
    # =========================================================================

    TestCase("Работаете в Астане?", ["coverage"], "regions", "Город"),
    TestCase("Есть в Алматы?", ["coverage"], "regions", "Город"),
    TestCase("доставка в Караганду", ["coverage"], "regions", "Доставка"),
    TestCase("по всему Казахстану работаете?", ["coverage"], "regions", "Страна"),
    TestCase("в регионах есть?", ["coverage"], "regions", "Регионы"),
    TestCase("можно в Шымкенте?", ["coverage"], "regions", "Город"),

    # =========================================================================
    # ПАРТНЁРСТВО
    # =========================================================================

    TestCase("Как стать партнёром?", ["partners"], "partnership", "Прямой вопрос"),
    TestCase("партнёрская программа", ["partners"], "partnership", "Программа"),
    TestCase("хочу продавать ваш продукт", ["partners"], "partnership", "Реселлер"),
    TestCase("условия для дилеров", ["partners"], "partnership", "Дилер"),
    TestCase("комиссия за привлечение", ["partners"], "partnership", "Комиссия"),

    # =========================================================================
    # ОБНОВЛЕНИЯ
    # =========================================================================

    TestCase("Что нового?", ["whats_new"], "updates", "Прямой вопрос"),
    TestCase("последние обновления", ["whats_new"], "updates", "Обновления"),
    TestCase("changelog", ["whats_new"], "updates", "Английский"),
    TestCase("новые функции добавили?", ["whats_new"], "updates", "Функции"),

    # =========================================================================
    # КЕЙСЫ
    # =========================================================================

    TestCase("Примеры внедрения", ["success_stories"], "cases", "Примеры"),
    TestCase("кто уже использует?", ["success_stories"], "cases", "Клиенты"),
    TestCase("отзывы клиентов", ["success_stories"], "cases", "Отзывы"),
    TestCase("результаты внедрения", ["success_stories"], "cases", "Результаты"),
    TestCase("кейсы", ["success_stories"], "cases", "Кейсы"),

    # =========================================================================
    # FAQ
    # =========================================================================

    TestCase("Нужен ли интернет?", ["common_questions"], "faq", "Интернет"),
    TestCase("можно офлайн работать?", ["common_questions"], "faq", "Офлайн"),
    TestCase("с нескольких устройств можно?", ["common_questions"], "faq", "Устройства"),
    TestCase("нужен ли кассовый аппарат", ["common_questions", "wipon_kassa"], "faq", "Касса"),
    TestCase("есть api?", ["common_questions"], "faq", "API"),
    TestCase("данные как долго хранятся", ["common_questions"], "faq", "Хранение"),

    # =========================================================================
    # ТРЕБОВАНИЯ
    # =========================================================================

    TestCase("Минимальные требования?", ["system_requirements"], "requirements", "Прямой вопрос"),
    TestCase("на каком телефоне работает", ["system_requirements"], "requirements", "Телефон"),
    TestCase("какой компьютер нужен", ["system_requirements"], "requirements", "ПК"),
    TestCase("windows 7 пойдёт?", ["system_requirements"], "requirements", "Windows"),
    TestCase("ios поддерживаете?", ["system_requirements"], "requirements", "iOS"),
    TestCase("android версия какая нужна", ["system_requirements"], "requirements", "Android"),
    TestCase("браузер какой лучше", ["system_requirements"], "requirements", "Браузер"),

    # =========================================================================
    # БЕЗОПАСНОСТЬ
    # =========================================================================

    TestCase("Как защищены данные?", ["data_protection"], "security", "Защита"),
    TestCase("безопасность данных", ["data_protection"], "security", "Безопасность"),
    TestCase("шифрование есть?", ["data_protection"], "security", "Шифрование"),
    TestCase("бэкапы делаете?", ["data_protection"], "security", "Бэкапы"),
    TestCase("данные не потеряются?", ["data_protection"], "security", "Потеря"),
    TestCase("резервное копирование", ["data_protection"], "security", "Резервное"),
    TestCase("gdpr соответствие", ["data_protection"], "security", "GDPR"),

    # =========================================================================
    # МИГРАЦИЯ
    # =========================================================================

    TestCase("Как перейти с 1С?", ["switching"], "migration", "1С"),
    TestCase("импорт из excel", ["switching"], "migration", "Excel"),
    TestCase("перенос данных", ["switching"], "migration", "Перенос"),
    TestCase("с другой программы перейти", ["switching"], "migration", "Другая программа"),
    TestCase("миграция базы товаров", ["switching"], "migration", "Миграция"),

    # =========================================================================
    # КОНКУРЕНТЫ
    # =========================================================================

    TestCase("Чем лучше iiko?", ["vs_others"], "competitors", "iiko"),
    TestCase("сравнение с r-keeper", ["vs_others"], "competitors", "R-Keeper"),
    TestCase("отличия от poster", ["vs_others"], "competitors", "Poster"),
    TestCase("почему не 1с", ["vs_others"], "competitors", "1С"),

    # =========================================================================
    # ПОДДЕРЖКА
    # =========================================================================

    TestCase("Есть техподдержка?", ["help"], "support", "Поддержка"),
    TestCase("обучение проводите?", ["help"], "support", "Обучение"),
    TestCase("помощь с настройкой", ["help"], "support", "Настройка"),
    TestCase("консультация", ["help"], "support", "Консультация"),

    # =========================================================================
    # КОНТАКТЫ
    # =========================================================================

    TestCase("Как с вами связаться?", ["how_to_contact"], "contacts", "Связь"),
    TestCase("телефон", ["how_to_contact"], "contacts", "Телефон"),
    TestCase("сайт какой", ["how_to_contact"], "contacts", "Сайт"),

    # =========================================================================
    # ДЛЯ КОГО
    # =========================================================================

    TestCase("Для кого подходит?", ["who_is_it_for"], "audience", "Аудитория"),
    TestCase("подойдёт для магазина?", ["who_is_it_for"], "audience", "Магазин"),
    TestCase("для ип на упрощёнке", ["who_is_it_for", "wipon_tis"], "audience", "ИП"),
    TestCase("для ресторана подойдёт?", ["who_is_it_for"], "audience", "Ресторан"),
    TestCase("для аптеки", ["who_is_it_for"], "audience", "Аптека"),

    # =========================================================================
    # ПРЕИМУЩЕСТВА
    # =========================================================================

    TestCase("Почему Wipon?", ["why_wipon"], "benefits", "Почему"),
    TestCase("ваши преимущества", ["why_wipon"], "benefits", "Преимущества"),
    TestCase("чем вы лучше", ["why_wipon"], "benefits", "Лучше"),
    TestCase("плюсы системы", ["why_wipon"], "benefits", "Плюсы"),

    # =========================================================================
    # СЛОЖНЫЕ И НЕСТАНДАРТНЫЕ ЗАПРОСЫ
    # =========================================================================

    # Эмоциональные
    TestCase("Помогите! Нужна касса срочно!", ["wipon_kassa"], "emotional", "Срочность"),
    TestCase("СКОЛЬКО ЭТО СТОИТ???", ["tariffs", "tariffs_detailed"], "emotional", "Caps Lock"),
    TestCase("Очень нужна помощь с учётом", ["inventory", "help"], "emotional", "Просьба"),

    # С ошибками
    TestCase("виопн касса", ["wipon_kassa"], "typos", "Опечатка в названии"),
    TestCase("whipon", ["overview"], "typos", "Английская опечатка"),
    TestCase("проверка алкоголья", ["wipon_pro"], "typos", "Опечатка"),

    # Смешанные языки
    TestCase("price list скиньте", ["tariffs", "tariffs_detailed"], "mixed", "Англ+рус"),
    TestCase("integration с kaspi есть?", ["marketplaces"], "mixed", "Англ+рус"),

    # Длинные запросы
    TestCase(
        "Здравствуйте, у меня небольшой магазин продуктов в Алматы, "
        "хочу автоматизировать учёт товаров и продажи, сколько это будет стоить?",
        ["tariffs", "tariffs_detailed", "who_is_it_for"],
        "long",
        "Длинный запрос"
    ),
    TestCase(
        "Мы сейчас работаем на 1С но хотим перейти на что-то более современное, "
        "можете рассказать как перенести данные и сколько стоит ваша система?",
        ["switching", "tariffs"],
        "long",
        "Длинный запрос про миграцию"
    ),

    # Очень короткие
    TestCase("цена", ["tariffs", "tariffs_detailed"], "short", "Одно слово"),
    TestCase("касса", ["wipon_kassa"], "short", "Одно слово"),
    TestCase("склад", ["inventory"], "short", "Одно слово"),
    TestCase("каспи", ["marketplaces"], "short", "Одно слово"),

    # Негативные/сомнения
    TestCase("а это не дорого?", ["tariffs", "free"], "objection", "Возражение о цене"),
    TestCase("а данные точно не потеряются?", ["data_protection"], "objection", "Возражение о безопасности"),
    TestCase("а вдруг сервера упадут?", ["data_protection"], "objection", "Возражение о надёжности"),
]


def run_tests(
    retriever: KnowledgeRetriever,
    test_cases: List[TestCase],
    verbose: bool = False
) -> Tuple[int, int, List[TestCase]]:
    """
    Запуск тестов.

    Returns:
        (passed, failed, failed_cases)
    """
    passed = 0
    failed = 0
    failed_cases = []

    for tc in test_cases:
        facts = retriever.retrieve(tc.query, top_k=3)

        # Проверяем, что хотя бы одна ожидаемая тема найдена
        found = False
        found_topics = []

        for section in WIPON_KNOWLEDGE.sections:
            if section.facts.strip() in facts:
                found_topics.append(section.topic)
                if section.topic in tc.expected_topics:
                    found = True

        if found:
            passed += 1
            if verbose:
                print(f"✓ [{tc.category}] {tc.description}: \"{tc.query[:40]}...\"")
        else:
            failed += 1
            failed_cases.append(tc)
            print(f"✗ [{tc.category}] {tc.description}")
            print(f"  Query: \"{tc.query}\"")
            print(f"  Expected: {tc.expected_topics}")
            print(f"  Found: {found_topics if found_topics else 'NOTHING'}")
            print()

    return passed, failed, failed_cases


def analyze_keywords(failed_cases: List[TestCase]):
    """Анализ пропущенных ключевых слов"""
    print("\n" + "=" * 60)
    print("АНАЛИЗ ПРОПУЩЕННЫХ КЛЮЧЕВЫХ СЛОВ")
    print("=" * 60)

    suggestions = {}

    for tc in failed_cases:
        query_words = set(tc.query.lower().split())

        for expected_topic in tc.expected_topics:
            section = WIPON_KNOWLEDGE.get_by_topic(expected_topic)
            if section:
                keywords = set(kw.lower() for kw in section.keywords)
                missing = query_words - keywords

                # Фильтруем стоп-слова
                stop_words = {'как', 'что', 'где', 'когда', 'есть', 'ли', 'в', 'на', 'с', 'и', 'а', 'у', 'к', 'по'}
                missing = missing - stop_words

                if missing:
                    key = f"{expected_topic} ({section.category})"
                    if key not in suggestions:
                        suggestions[key] = set()
                    suggestions[key].update(missing)

    for topic, words in sorted(suggestions.items()):
        print(f"\n{topic}:")
        print(f"  Добавить keywords: {sorted(words)}")


def main():
    parser = argparse.ArgumentParser(description="Стресс-тест базы знаний")
    parser.add_argument("--verbose", "-v", action="store_true", help="Показывать успешные тесты")
    parser.add_argument("--category", "-c", help="Фильтр по категории теста")
    parser.add_argument("--analyze", "-a", action="store_true", help="Анализ пропущенных keywords")
    args = parser.parse_args()

    print("=" * 60)
    print("СТРЕСС-ТЕСТ БАЗЫ ЗНАНИЙ WIPON")
    print("=" * 60)
    print()

    retriever = KnowledgeRetriever(use_embeddings=False)

    # Фильтрация по категории
    test_cases = TEST_CASES
    if args.category:
        test_cases = [tc for tc in TEST_CASES if tc.category == args.category]
        print(f"Фильтр: категория = {args.category}")
        print()

    print(f"Всего тестов: {len(test_cases)}")
    print()

    passed, failed, failed_cases = run_tests(retriever, test_cases, args.verbose)

    print()
    print("=" * 60)
    print(f"РЕЗУЛЬТАТ: {passed}/{len(test_cases)} тестов прошли ({100*passed/len(test_cases):.1f}%)")
    print(f"Провалено: {failed}")
    print("=" * 60)

    if args.analyze and failed_cases:
        analyze_keywords(failed_cases)

    # Статистика по категориям
    if not args.category:
        print("\nСТАТИСТИКА ПО КАТЕГОРИЯМ:")
        categories = {}
        for tc in TEST_CASES:
            if tc.category not in categories:
                categories[tc.category] = {"total": 0, "failed": 0}
            categories[tc.category]["total"] += 1

        for tc in failed_cases:
            categories[tc.category]["failed"] += 1

        for cat in sorted(categories.keys()):
            stats = categories[cat]
            passed_cat = stats["total"] - stats["failed"]
            pct = 100 * passed_cat / stats["total"]
            status = "✓" if stats["failed"] == 0 else "✗"
            print(f"  {status} {cat}: {passed_cat}/{stats['total']} ({pct:.0f}%)")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
