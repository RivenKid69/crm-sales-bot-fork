#!/usr/bin/env python3
"""
Тест новых секций 1100-1200.

Проверяем точность попадания в новые секции.
По 5 уникальных клиентских запросов на каждую секцию.

Запуск: python3 check_new_sections_1100_1200.py
"""

import sys
import os
import time
import requests
from typing import List, Tuple
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from src.knowledge.category_router import CategoryRouter
from src.knowledge.retriever import KnowledgeRetriever

# =============================================================================
# Тестовые запросы для новых секций 1100-1200
# Формат: (запрос, ожидаемая_категория, ожидаемый_topic, описание)
# =============================================================================

TEST_QUERIES: List[Tuple[str, str, str, str]] = [
    # ==========================================================================
    # integrations_marking_support_1167 - маркировка товаров
    # ==========================================================================
    ("Ваша система работает с маркировкой?", "integrations", "integrations_marking_support_1167", "маркировка общий"),
    ("Можно продавать маркированный алкоголь и табак?", "integrations", "integrations_marking_support_1167", "алкоголь табак маркировка"),
    ("Поддерживается ли маркировка товаров в wipon?", "integrations", "integrations_marking_support_1167", "поддержка маркировки"),
    ("Работает с маркированными товарами?", "integrations", "integrations_marking_support_1167", "маркированные товары"),
    ("У вас есть функция маркировки для алкоголя?", "integrations", "integrations_marking_support_1167", "функция маркировки"),

    # ==========================================================================
    # integrations_kaspi_qr_1173 - оплата через Kaspi QR
    # ==========================================================================
    ("Можно оплатить каспи кьюар?", "integrations", "integrations_kaspi_qr_1173", "kaspi qr опечатка"),
    ("Принимаете kaspi qr на кассе?", "integrations", "integrations_kaspi_qr_1173", "kaspi qr касса"),
    ("QR оплата через каспи работает?", "integrations", "integrations_kaspi_qr_1173", "qr каспи"),
    ("Клиенты могут платить через каспи qr код?", "integrations", "integrations_kaspi_qr_1173", "клиенты qr код"),
    ("Поддерживаете ли kaspi qr оплату?", "integrations", "integrations_kaspi_qr_1173", "поддержка qr"),

    # ==========================================================================
    # integrations_online_shop_manual_1177 - интернет-магазин вручную
    # ==========================================================================
    ("Можно подключить к своему интернет-магазину?", "integrations", "integrations_online_shop_manual_1177", "свой интернет магазин"),
    ("Есть интеграция с онлайн магазином?", "integrations", "integrations_online_shop_manual_1177", "онлайн магазин интеграция"),
    ("Как связать wipon с сайтом интернет-магазина?", "integrations", "integrations_online_shop_manual_1177", "связь с сайтом"),
    ("Синхронизация с интернет-магазином возможна?", "integrations", "integrations_online_shop_manual_1177", "синхронизация"),
    ("Выгрузка в интернет-магазин есть?", "integrations", "integrations_online_shop_manual_1177", "выгрузка"),

    # ==========================================================================
    # integrations_alcohol_datamatrix_1179 - учёт алкоголя с DataMatrix
    # ==========================================================================
    ("Как вести учёт алкогольной продукции?", "integrations", "integrations_alcohol_datamatrix_1179", "учёт алкоголя"),
    ("Программа работает с DataMatrix для алкоголя?", "integrations", "integrations_alcohol_datamatrix_1179", "datamatrix алкоголь"),
    ("Можно учитывать спиртные напитки с маркировкой?", "integrations", "integrations_alcohol_datamatrix_1179", "спиртное маркировка"),
    ("Поддерживает учёт алкоголя через datamatrix?", "integrations", "integrations_alcohol_datamatrix_1179", "datamatrix поддержка"),
    ("Алкоголь с кодами datamatrix ведётся?", "integrations", "integrations_alcohol_datamatrix_1179", "коды datamatrix"),

    # ==========================================================================
    # products_food_store_kz_1178 - продуктовый магазин (казахский)
    # ==========================================================================
    ("Азық-түлік дүкеніне бағдарлама керек", "products", "products_food_store_kz_1178", "азық-түлік дүкені"),
    ("Wipon азық-түлікке қолайлы ма?", "products", "products_food_store_kz_1178", "азық-түлік қолайлы"),
    ("Продуктовый дүкенге wipon жарай ма?", "products", "products_food_store_kz_1178", "продуктовый дүкен"),
    ("Азық-түлік сату үшін программа бар ма?", "products", "products_food_store_kz_1178", "азық-түлік сату"),
    ("Жемістер мен көкөністер сатуға программа", "products", "products_food_store_kz_1178", "жемістер көкөністер"),

    # ==========================================================================
    # features_product_photos_1118 - фото товаров
    # ==========================================================================
    ("Можно фото товаров загружать?", "features", "features_product_photos_1118", "загрузка фото"),
    ("Есть возможность добавить картинку к товару?", "features", "features_product_photos_1118", "картинка товара"),
    ("Фотографии в карточках товаров?", "features", "features_product_photos_1118", "фото карточка"),
    ("Изображения товаров можно добавить?", "features", "features_product_photos_1118", "изображения"),
    ("Поддерживает ли программа фото товаров?", "features", "features_product_photos_1118", "поддержка фото"),

    # ==========================================================================
    # features_delivery_service_1119 - доставка Glovo/Яндекс
    # ==========================================================================
    ("Работаете с Glovo доставкой?", "features", "features_delivery_service_1119", "glovo"),
    ("Можно учитывать заказы с яндекс доставки?", "features", "features_delivery_service_1119", "яндекс доставка"),
    ("Интеграция с сервисами доставки есть?", "features", "features_delivery_service_1119", "сервисы доставки"),
    ("Доставка через glovo или яндекс учитывается?", "features", "features_delivery_service_1119", "glovo яндекс"),
    ("Подойдёт для бизнеса с доставкой?", "features", "features_delivery_service_1119", "бизнес доставка"),

    # ==========================================================================
    # features_services_accounting_1187 - учёт услуг
    # ==========================================================================
    ("Можно вести учёт услуг, а не товаров?", "features", "features_services_accounting_1187", "учёт услуг"),
    ("Подходит для услуг, не только товаров?", "features", "features_services_accounting_1187", "услуги не товары"),
    ("Как добавить услугу вместо товара?", "features", "features_services_accounting_1187", "добавить услугу"),
    ("Услуги можно пробивать через кассу?", "features", "features_services_accounting_1187", "пробивать услуги"),
    ("У меня салон красоты, можно услуги учитывать?", "features", "features_services_accounting_1187", "салон услуги"),

    # ==========================================================================
    # features_power_outage_1188 - работа при отключении электричества
    # ==========================================================================
    ("Что делать если отключили свет?", "features", "features_power_outage_1188", "отключение света"),
    ("Работает ли при отключении электричества?", "features", "features_power_outage_1188", "без электричества"),
    ("Если нет питания, можно работать?", "features", "features_power_outage_1188", "нет питания"),
    ("Что будет когда электричество вырубят?", "features", "features_power_outage_1188", "вырубят электричество"),
    ("Временно нет электричества, как работать?", "features", "features_power_outage_1188", "временно нет"),

    # ==========================================================================
    # features_multiple_users_1189 - несколько пользователей
    # ==========================================================================
    ("Можно несколько человек подключить?", "features", "features_multiple_users_1189", "несколько человек"),
    ("Много пользователей на один аккаунт?", "features", "features_multiple_users_1189", "много пользователей"),
    ("Можно ли подключить нескольких сотрудников?", "features", "features_multiple_users_1189", "несколько сотрудников"),
    ("Разные права доступа для разных людей?", "features", "features_multiple_users_1189", "разные права"),
    ("Как добавить второго пользователя?", "features", "features_multiple_users_1189", "второй пользователь"),

    # ==========================================================================
    # features_kazakh_interface_1191 - казахский интерфейс
    # ==========================================================================
    ("Программа на казахском языке есть?", "features", "features_kazakh_interface_1191", "казахский язык"),
    ("Қазақ тілінде интерфейс бар ма?", "features", "features_kazakh_interface_1191", "қазақ тілі"),
    ("Можно переключить на казахский?", "features", "features_kazakh_interface_1191", "переключить казахский"),
    ("Интерфейс қазақша жұмыс істей ме?", "features", "features_kazakh_interface_1191", "интерфейс қазақша"),
    ("Есть ли казахский язык в интерфейсе?", "features", "features_kazakh_interface_1191", "язык интерфейс"),
]


# =============================================================================
# LLM клиент
# =============================================================================

class OllamaLLM:
    def __init__(self, model: str = "qwen3:8b"):
        self.model = model
        self.base_url = "http://localhost:11434/api/generate"

    def generate(self, prompt: str) -> str:
        response = requests.post(
            self.base_url,
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "think": False,
                "options": {"temperature": 0.0, "num_predict": 100}
            },
            timeout=60
        )
        if response.status_code == 200:
            return response.json().get("response", "")
        raise RuntimeError(f"Ollama error: {response.status_code}")


def is_ollama_available() -> bool:
    try:
        return requests.get("http://localhost:11434/api/tags", timeout=2).status_code == 200
    except:
        return False


def get_available_model() -> str:
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        if response.status_code == 200:
            models = [m["name"] for m in response.json().get("models", [])]
            for preferred in ["qwen3:8b-fast", "qwen3:8b", "qwen3:1.7b"]:
                if preferred in models:
                    return preferred
            return models[0] if models else "qwen3:8b"
    except:
        return "qwen3:8b"


@dataclass
class TestResult:
    query: str
    expected_category: str
    expected_topic: str
    description: str
    predicted_categories: List[str]
    retrieved_topics: List[str]
    category_correct: bool
    topic_found: bool
    latency_ms: float


def run_tests() -> List[TestResult]:
    if not is_ollama_available():
        print("ERROR: Ollama не доступен. Запустите: ollama serve")
        sys.exit(1)

    model = get_available_model()
    print(f"Модель: {model}")
    print(f"Всего тестов: {len(TEST_QUERIES)}")
    print("=" * 120)

    llm = OllamaLLM(model)
    router = CategoryRouter(llm, top_k=3, fallback_categories=["support", "faq"])
    retriever = KnowledgeRetriever()

    results: List[TestResult] = []
    start_total = time.perf_counter()

    for i, (query, expected_cat, expected_topic, description) in enumerate(TEST_QUERIES, 1):
        print(f"[{i:3d}/{len(TEST_QUERIES)}] {query[:55]:<55}", end=" ")

        start = time.perf_counter()
        try:
            # 1. Получаем категории от роутера
            predicted_cats = router.route(query)

            # 2. Ищем в базе знаний
            results_kb = retriever.search(query, categories=predicted_cats, top_k=5)
            retrieved_topics = [r.topic for r in results_kb]

        except Exception as e:
            print(f"ERROR: {e}")
            predicted_cats = []
            retrieved_topics = []

        latency = (time.perf_counter() - start) * 1000

        category_correct = expected_cat in predicted_cats
        topic_found = expected_topic in retrieved_topics

        results.append(TestResult(
            query=query,
            expected_category=expected_cat,
            expected_topic=expected_topic,
            description=description,
            predicted_categories=predicted_cats,
            retrieved_topics=retrieved_topics,
            category_correct=category_correct,
            topic_found=topic_found,
            latency_ms=latency
        ))

        # Статус вывода
        cat_status = "OK" if category_correct else "FAIL"
        topic_status = "OK" if topic_found else "MISS"
        print(f"[Cat:{cat_status}|Topic:{topic_status}] {predicted_cats} ({latency:.0f}ms)")

        if not topic_found and category_correct:
            print(f"           -> Topics: {retrieved_topics[:3]}")

    print(f"\nОбщее время: {time.perf_counter() - start_total:.1f}s")
    return results


def print_summary(results: List[TestResult]):
    print("\n" + "=" * 120)
    print("ИТОГИ ТЕСТА НОВЫХ СЕКЦИЙ 1100-1200")
    print("=" * 120)

    cat_correct = sum(1 for r in results if r.category_correct)
    topic_found = sum(1 for r in results if r.topic_found)
    total = len(results)

    cat_accuracy = cat_correct / total * 100
    topic_accuracy = topic_found / total * 100

    print(f"\nТочность категорий: {cat_correct}/{total} ({cat_accuracy:.1f}%)")
    print(f"Точность топиков:   {topic_found}/{total} ({topic_accuracy:.1f}%)")
    print(f"Средняя латентность: {sum(r.latency_ms for r in results) / len(results):.0f}ms")

    # Группировка по секциям
    print("\nТочность по секциям:")
    print("-" * 80)

    sections = {}
    for r in results:
        topic = r.expected_topic
        if topic not in sections:
            sections[topic] = {"cat_ok": 0, "topic_ok": 0, "total": 0}
        sections[topic]["total"] += 1
        if r.category_correct:
            sections[topic]["cat_ok"] += 1
        if r.topic_found:
            sections[topic]["topic_ok"] += 1

    for topic, stats in sorted(sections.items()):
        cat_acc = stats["cat_ok"] / stats["total"] * 100
        topic_acc = stats["topic_ok"] / stats["total"] * 100
        status = "OK" if topic_acc >= 60 else "LOW"
        print(f"  {topic[:45]:<45}: Cat {stats['cat_ok']}/{stats['total']} | Topic {stats['topic_ok']}/{stats['total']} ({topic_acc:.0f}%) [{status}]")

    # Ошибки
    failures = [r for r in results if not r.topic_found]
    if failures:
        print(f"\n{'=' * 120}")
        print(f"ПРОМАХИ ПО ТОПИКАМ ({len(failures)}):")
        print("-" * 120)
        for i, r in enumerate(failures, 1):
            print(f"{i:2d}. {r.query[:70]}")
            print(f"    Ожидал топик: {r.expected_topic}")
            print(f"    Категории: {r.predicted_categories}")
            print(f"    Найдено: {r.retrieved_topics[:3]}")
            print()


def main():
    print("=" * 120)
    print("ТЕСТ НОВЫХ СЕКЦИЙ 1100-1200 (11 секций, 55 запросов)")
    print("=" * 120)

    results = run_tests()
    print_summary(results)

    topic_accuracy = sum(1 for r in results if r.topic_found) / len(results) * 100
    print(f"\nРезультат: {'PASSED' if topic_accuracy >= 60 else 'FAILED'} (топики: {topic_accuracy:.1f}%)")
    sys.exit(0 if topic_accuracy >= 60 else 1)


if __name__ == "__main__":
    main()
