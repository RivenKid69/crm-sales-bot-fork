#!/usr/bin/env python3
"""
Тест новых секций 1100-1200 только по ключевым словам.
Без LLM и эмбеддингов - чистый keyword matching.

Запуск: python3 check_new_sections_keywords.py
"""

import sys
import os
from typing import List, Tuple
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from knowledge.loader import load_knowledge_base

# =============================================================================
# Тестовые запросы для новых секций
# =============================================================================

TEST_QUERIES: List[Tuple[str, str, str]] = [
    # integrations_marking_support_1167
    ("Ваша система работает с маркировкой?", "integrations_marking_support_1167", "маркировка общий"),
    ("Можно продавать маркированный алкоголь?", "integrations_marking_support_1167", "алкоголь маркировка"),
    ("Поддерживается маркировка товаров?", "integrations_marking_support_1167", "поддержка маркировки"),
    ("Работает с маркированными товарами?", "integrations_marking_support_1167", "маркированные товары"),
    ("Маркировка алкоголя и табака есть?", "integrations_marking_support_1167", "маркировка табак"),

    # integrations_kaspi_qr_1173
    ("Можно оплатить kaspi qr?", "integrations_kaspi_qr_1173", "kaspi qr"),
    ("Принимаете оплату через каспи qr?", "integrations_kaspi_qr_1173", "каспи qr"),
    ("QR оплата kaspi работает?", "integrations_kaspi_qr_1173", "qr kaspi"),
    ("Касса поддерживает kaspi qr?", "integrations_kaspi_qr_1173", "касса qr"),
    ("Оплата через kaspi qr код", "integrations_kaspi_qr_1173", "qr код"),

    # integrations_online_shop_manual_1177
    ("Можно подключить интернет-магазин?", "integrations_online_shop_manual_1177", "интернет магазин"),
    ("Есть интеграция с онлайн магазином?", "integrations_online_shop_manual_1177", "онлайн магазин"),
    ("Выгрузка в интернет магазин?", "integrations_online_shop_manual_1177", "выгрузка"),
    ("Синхронизация с интернет-магазином?", "integrations_online_shop_manual_1177", "синхронизация"),
    ("ecommerce интеграция есть?", "integrations_online_shop_manual_1177", "ecommerce"),

    # integrations_alcohol_datamatrix_1179
    ("Учёт алкоголя через систему?", "integrations_alcohol_datamatrix_1179", "учёт алкоголя"),
    ("Алкоголь с маркировкой datamatrix", "integrations_alcohol_datamatrix_1179", "datamatrix"),
    ("Вести учёт алкоголя можно?", "integrations_alcohol_datamatrix_1179", "вести алкоголь"),
    ("Маркировка алкоголя datamatrix", "integrations_alcohol_datamatrix_1179", "маркировка datamatrix"),
    ("Спиртное с datamatrix учёт", "integrations_alcohol_datamatrix_1179", "спиртное"),

    # products_food_store_kz_1178
    ("Азық-түлік дүкеніне бағдарлама", "products_food_store_kz_1178", "азық-түлік дүкені"),
    ("Wipon азық-түлікке қолайлы?", "products_food_store_kz_1178", "азық-түлік"),
    ("Продуктовый дүкенге wipon", "products_food_store_kz_1178", "дүкен"),
    ("Азық-түлік сату программа", "products_food_store_kz_1178", "сату"),
    ("Азық-түлік дүкеніне қолайлы ма", "products_food_store_kz_1178", "қолайлы"),

    # features_product_photos_1118
    ("Добавить фото товаров можно?", "features_product_photos_1118", "фото товаров"),
    ("Карточка товара с фото", "features_product_photos_1118", "карточка фото"),
    ("Фотография товара в программе", "features_product_photos_1118", "фотография"),
    ("Изображение товара добавить", "features_product_photos_1118", "изображение"),
    ("Фото товаров в программу", "features_product_photos_1118", "фото программу"),

    # features_delivery_service_1119
    ("Бизнес с доставкой подойдёт?", "features_delivery_service_1119", "бизнес доставкой"),
    ("Доставка glovo яндекс", "features_delivery_service_1119", "glovo яндекс"),
    ("Учитывать заказы доставку", "features_delivery_service_1119", "заказы доставку"),
    ("Программа для доставки товаров", "features_delivery_service_1119", "программа доставки"),
    ("Glovo яндекс доставка учёт", "features_delivery_service_1119", "glovo доставка"),

    # features_services_accounting_1187
    ("Можно вести учёт услуг?", "features_services_accounting_1187", "учёт услуг"),
    ("Не только товары, услуги тоже", "features_services_accounting_1187", "товары услуги"),
    ("Услуги как позиции добавить", "features_services_accounting_1187", "услуги позиции"),
    ("Услуги через кассу пробить", "features_services_accounting_1187", "услуги касса"),
    ("Вести учёт услуг в программе", "features_services_accounting_1187", "вести услуг"),

    # features_power_outage_1188
    ("Отключили электричество что делать?", "features_power_outage_1188", "отключили электричество"),
    ("Работает без электричества?", "features_power_outage_1188", "без электричества"),
    ("Временно нет питания как работать", "features_power_outage_1188", "нет питания"),
    ("Мобильное приложение без электричества", "features_power_outage_1188", "мобильное электричество"),
    ("Работа при отключении света", "features_power_outage_1188", "отключении света"),

    # features_multiple_users_1189
    ("Несколько пользователей в аккаунте", "features_multiple_users_1189", "несколько пользователей"),
    ("Один аккаунт много пользователей", "features_multiple_users_1189", "один аккаунт"),
    ("Разные права доступа пользователям", "features_multiple_users_1189", "права доступа"),
    ("Подключить много пользователей", "features_multiple_users_1189", "много пользователей"),
    ("Несколько пользователей система", "features_multiple_users_1189", "пользователей система"),

    # features_kazakh_interface_1191
    ("Программа на казахском языке?", "features_kazakh_interface_1191", "казахский язык"),
    ("Қазақ тіліндегі интерфейс", "features_kazakh_interface_1191", "қазақ тілі"),
    ("Интерфейс қазақша есть?", "features_kazakh_interface_1191", "интерфейс қазақша"),
    ("Язык интерфейса казахский", "features_kazakh_interface_1191", "язык интерфейс"),
    ("Переключить на казахский язык", "features_kazakh_interface_1191", "переключить казахский"),
]


@dataclass
class TestResult:
    query: str
    expected_topic: str
    description: str
    matched_topics: List[str]
    topic_found: bool
    score: float


def keyword_match_score(query: str, keywords: List[str]) -> float:
    """Простой скоринг по совпадению ключевых слов."""
    query_lower = query.lower()
    matches = 0
    for kw in keywords:
        if kw.lower() in query_lower:
            matches += 1
    return matches / max(len(keywords), 1)


def run_tests() -> List[TestResult]:
    print("Загружаем базу знаний...")
    kb = load_knowledge_base()
    print(f"Загружено секций: {len(kb.sections)}")
    print(f"Всего тестов: {len(TEST_QUERIES)}")
    print("=" * 100)

    results = []

    for i, (query, expected_topic, description) in enumerate(TEST_QUERIES, 1):
        print(f"[{i:3d}/{len(TEST_QUERIES)}] {query[:50]:<50}", end=" ")

        # Считаем score для каждой секции
        scores = []
        for section in kb.sections:
            score = keyword_match_score(query, section.keywords)
            if score > 0:
                scores.append((section.topic, score))

        # Сортируем по score
        scores.sort(key=lambda x: -x[1])
        top_topics = [t for t, s in scores[:5]]
        best_score = scores[0][1] if scores else 0

        topic_found = expected_topic in top_topics

        results.append(TestResult(
            query=query,
            expected_topic=expected_topic,
            description=description,
            matched_topics=top_topics,
            topic_found=topic_found,
            score=best_score
        ))

        status = "OK" if topic_found else "MISS"
        print(f"[{status}] {top_topics[:2] if top_topics else '[]'}")

    return results


def print_summary(results: List[TestResult]):
    print("\n" + "=" * 100)
    print("ИТОГИ ТЕСТА НОВЫХ СЕКЦИЙ (keyword matching)")
    print("=" * 100)

    found = sum(1 for r in results if r.topic_found)
    total = len(results)
    accuracy = found / total * 100

    print(f"\nТочность попадания в топик: {found}/{total} ({accuracy:.1f}%)")

    # Группировка по секциям
    print("\nТочность по секциям:")
    print("-" * 70)

    sections = {}
    for r in results:
        topic = r.expected_topic
        if topic not in sections:
            sections[topic] = {"found": 0, "total": 0}
        sections[topic]["total"] += 1
        if r.topic_found:
            sections[topic]["found"] += 1

    for topic, stats in sorted(sections.items()):
        acc = stats["found"] / stats["total"] * 100
        status = "OK" if acc >= 60 else "LOW"
        print(f"  {topic[:45]:<45}: {stats['found']}/{stats['total']} ({acc:.0f}%) [{status}]")

    # Ошибки
    failures = [r for r in results if not r.topic_found]
    if failures:
        print(f"\n{'=' * 100}")
        print(f"ПРОМАХИ ({len(failures)}):")
        print("-" * 100)
        for i, r in enumerate(failures[:15], 1):
            print(f"{i:2d}. {r.query[:60]}")
            print(f"    Ожидал: {r.expected_topic}")
            print(f"    Нашёл: {r.matched_topics[:3]}")


def main():
    print("=" * 100)
    print("ТЕСТ KEYWORD MATCHING ДЛЯ НОВЫХ СЕКЦИЙ 1100-1200")
    print("=" * 100)

    results = run_tests()
    print_summary(results)

    accuracy = sum(1 for r in results if r.topic_found) / len(results) * 100
    print(f"\nРезультат: {'PASSED' if accuracy >= 60 else 'NEEDS WORK'} ({accuracy:.1f}%)")


if __name__ == "__main__":
    main()
