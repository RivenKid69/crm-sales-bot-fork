#!/usr/bin/env python3
"""
Скрипт для тестирования базы знаний.
Запуск: python scripts/test_knowledge_base.py
"""

import sys
sys.path.insert(0, 'src')

from src.knowledge.retriever import KnowledgeRetriever
from src.knowledge.data import WIPON_KNOWLEDGE


def test_interactive():
    """Интерактивный режим тестирования"""
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ БАЗЫ ЗНАНИЙ WIPON")
    print("=" * 60)
    print()

    # Показываем структуру базы
    print("📊 СТРУКТУРА БАЗЫ ЗНАНИЙ:")
    print("-" * 40)
    categories = {}
    for section in WIPON_KNOWLEDGE.sections:
        if section.category not in categories:
            categories[section.category] = []
        categories[section.category].append(section.topic)

    for cat, topics in categories.items():
        print(f"  {cat}: {', '.join(topics)}")
    print()

    # Инициализация retriever
    print("🔄 Инициализация retriever...")
    retriever = KnowledgeRetriever(use_embeddings=True)
    print(f"✓ Эмбеддинги: {'активны' if retriever.use_embeddings else 'отключены'}")
    print()

    # Интерактивный режим
    print("=" * 60)
    print("ИНТЕРАКТИВНЫЙ РЕЖИМ")
    print("Введите вопрос клиента для проверки поиска")
    print("Команды: /list, /section <topic>, /quit")
    print("=" * 60)
    print()

    while True:
        try:
            query = input("Вопрос: ").strip()

            if not query:
                continue

            if query == "/quit":
                break

            if query == "/list":
                print("\nВсе секции:")
                for i, s in enumerate(WIPON_KNOWLEDGE.sections, 1):
                    print(f"  {i}. [{s.category}] {s.topic} (priority={s.priority})")
                print()
                continue

            if query.startswith("/section "):
                topic = query.replace("/section ", "").strip()
                section = WIPON_KNOWLEDGE.get_by_topic(topic)
                if section:
                    print(f"\n=== {section.topic} ===")
                    print(f"Category: {section.category}")
                    print(f"Priority: {section.priority}")
                    print(f"Keywords: {', '.join(section.keywords)}")
                    print(f"\nFacts:\n{section.facts}")
                else:
                    print(f"Секция '{topic}' не найдена")
                print()
                continue

            # Поиск
            print()
            print("🔍 Результаты поиска:")
            print("-" * 40)

            # Без интента
            facts = retriever.retrieve(query, top_k=2)
            if facts:
                print(facts[:500])
                if len(facts) > 500:
                    print("... (обрезано)")
            else:
                print("❌ Ничего не найдено")

            print()

        except KeyboardInterrupt:
            print("\n\nВыход")
            break


def test_coverage():
    """Тест покрытия - проверяем что все секции находятся"""
    print("=" * 60)
    print("ТЕСТ ПОКРЫТИЯ БАЗЫ ЗНАНИЙ")
    print("=" * 60)
    print()

    retriever = KnowledgeRetriever(use_embeddings=False)

    # Тестовые запросы для каждой секции
    test_cases = [
        # (запрос, ожидаемые слова в результате)
        ("Какие продукты есть?", ["Wipon Desktop", "Wipon Kassa"]),
        ("Расскажи про кассу", ["касса", "ОФД"]),
        ("Проверка алкоголя", ["УКМ", "алкоголь"]),
        ("Wipon Desktop", ["учёт товаров", "ПК"]),
        ("Упрощёнка налоги", ["ТИС", "910"]),
        ("Программа лояльности", ["бонус", "Cashback"]),
        ("Мобильное приложение", ["телефон", "iOS"]),
        ("Складской учёт", ["остатки", "приёмка"]),
        ("Аналитика отчёты", ["ABC", "статистика"]),
        ("Сотрудники зарплата", ["Кадровый", "сотрудников"]),
        ("Интеграция Kaspi", ["Kaspi", "маркетплейс"]),
        ("Оплата картой терминал", ["POS", "эквайринг"]),
        ("Маркировка товаров", ["QR", "штрихкод"]),
        ("Интеграция 1С", ["1С", "бухгалтерия"]),
        ("Сколько стоит тариф", ["Mini", "тариф"]),
        ("Цена Wipon Pro", ["12,000", "смартфон"]),
        ("Бесплатно пробный", ["бесплатн", "Kassa"]),
        ("Для кого подходит", ["ИП", "магазин"]),
        ("Почему выбрать Wipon", ["преимущ", "50,000"]),
        ("Сравнение с iiko", ["iiko", "дешевле"]),
        ("Техподдержка обучение", ["поддержка", "100+"]),
        ("Контакты сайт", ["wipon.kz", "сайт"]),
    ]

    passed = 0
    failed = 0

    for query, expected_words in test_cases:
        facts = retriever.retrieve(query, top_k=2)
        facts_lower = facts.lower()

        found = any(word.lower() in facts_lower for word in expected_words)
        status = "✓" if found else "✗"

        if found:
            passed += 1
        else:
            failed += 1

        print(f"{status} '{query}'")
        if not found:
            print(f"   Ожидалось: {expected_words}")
            print(f"   Получено: {facts[:100]}...")

    print()
    print(f"Результат: {passed}/{passed+failed} тестов пройдено")
    print(f"Покрытие: {passed/(passed+failed)*100:.0f}%")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--coverage":
        test_coverage()
    else:
        test_interactive()
