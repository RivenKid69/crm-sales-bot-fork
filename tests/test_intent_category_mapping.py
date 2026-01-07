"""
Тесты для проверки корректности маппинга INTENT_TO_CATEGORY.

Проверяют что:
1. Все категории в маппинге существуют в базе знаний
2. Retriever возвращает результаты для интентов с категориями
3. Нет "мёртвых" категорий которые не существуют
"""

import pytest
import sys
from pathlib import Path

# Добавляем src в путь
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from knowledge.retriever import INTENT_TO_CATEGORY, CascadeRetriever
from knowledge.loader import load_knowledge_base


class TestIntentToCategoryMapping:
    """Тесты маппинга интентов на категории."""

    @pytest.fixture(scope="class")
    def knowledge_base(self):
        """Загружаем базу знаний один раз для всех тестов."""
        return load_knowledge_base()

    @pytest.fixture(scope="class")
    def real_categories(self, knowledge_base):
        """Получаем реальные категории из базы знаний."""
        return set(section.category for section in knowledge_base.sections)

    @pytest.fixture(scope="class")
    def retriever(self):
        """Создаём retriever без эмбеддингов для быстрых тестов."""
        return CascadeRetriever(use_embeddings=False)

    def test_all_categories_exist_in_knowledge_base(self, real_categories):
        """
        КРИТИЧЕСКИЙ ТЕСТ: Все категории из INTENT_TO_CATEGORY
        должны существовать в базе знаний.

        Если этот тест падает — retriever не найдёт факты для этих интентов!
        """
        all_used_categories = set()
        missing_categories = {}

        for intent, categories in INTENT_TO_CATEGORY.items():
            for cat in categories:
                all_used_categories.add(cat)
                if cat not in real_categories:
                    if cat not in missing_categories:
                        missing_categories[cat] = []
                    missing_categories[cat].append(intent)

        assert not missing_categories, (
            f"Найдены несуществующие категории в INTENT_TO_CATEGORY:\n"
            + "\n".join(
                f"  - '{cat}' используется в: {intents}"
                for cat, intents in missing_categories.items()
            )
            + f"\n\nДоступные категории: {sorted(real_categories)}"
        )

    def test_real_categories_list(self, real_categories):
        """Проверяем что база знаний содержит ожидаемые категории."""
        expected_categories = {
            "equipment", "products", "pricing", "support", "tis",
            "regions", "features", "inventory", "integrations",
            "analytics", "employees", "stability", "fiscal",
            "mobile", "promotions", "competitors", "faq"
        }

        assert expected_categories.issubset(real_categories), (
            f"В базе знаний отсутствуют ожидаемые категории: "
            f"{expected_categories - real_categories}"
        )

    def test_action_intents_have_categories(self):
        """
        Интенты действий (callback, demo, contact) должны иметь категории
        для поиска контактной информации.
        """
        action_intents = [
            "callback_request",
            "demo_request",
            "consultation_request",
            "contact_provided",
        ]

        for intent in action_intents:
            assert intent in INTENT_TO_CATEGORY, f"Интент '{intent}' не в маппинге"
            categories = INTENT_TO_CATEGORY[intent]
            assert len(categories) > 0, (
                f"Интент '{intent}' должен иметь категории для поиска контактов"
            )

    def test_objection_intents_have_categories(self):
        """Интенты возражений должны иметь категории для аргументов."""
        objection_intents = [
            "objection_competitor",
            "objection_price",
            "objection_no_time",
            "objection_think",
        ]

        for intent in objection_intents:
            assert intent in INTENT_TO_CATEGORY, f"Интент '{intent}' не в маппинге"
            categories = INTENT_TO_CATEGORY[intent]
            assert len(categories) > 0, (
                f"Интент '{intent}' должен иметь категории для аргументов"
            )

    def test_neutral_intents_have_empty_categories(self):
        """Нейтральные интенты не должны искать в базе знаний."""
        neutral_intents = [
            "greeting",
            "rejection",
            "farewell",
            "gratitude",
            "small_talk",
            "unclear",
        ]

        for intent in neutral_intents:
            assert intent in INTENT_TO_CATEGORY, f"Интент '{intent}' не в маппинге"
            categories = INTENT_TO_CATEGORY[intent]
            assert categories == [], (
                f"Нейтральный интент '{intent}' не должен иметь категорий, "
                f"но имеет: {categories}"
            )


class TestRetrieverWithCategories:
    """Тесты что retriever реально находит результаты."""

    @pytest.fixture(scope="class")
    def retriever(self):
        """Retriever без эмбеддингов для скорости."""
        return CascadeRetriever(use_embeddings=False)

    @pytest.mark.parametrize("intent,query", [
        ("price_question", "сколько стоит"),
        ("pricing_details", "какие тарифы"),
        ("question_features", "какие функции"),
        ("question_integrations", "с чем интегрируется"),
        ("comparison", "чем лучше конкурентов"),
        ("objection_competitor", "у нас уже есть iiko"),
        ("objection_price", "дорого"),
        ("demo_request", "хочу демо"),
        ("callback_request", "перезвоните"),
    ])
    def test_retriever_finds_results_for_intent(self, retriever, intent, query):
        """Retriever должен находить результаты для интентов с категориями."""
        categories = INTENT_TO_CATEGORY.get(intent, [])

        if not categories:
            pytest.skip(f"Интент '{intent}' не имеет категорий")

        # Ищем с категориями из маппинга
        results = retriever.search(query, categories=categories, top_k=3)

        assert len(results) > 0, (
            f"Retriever не нашёл результатов для интента '{intent}' "
            f"с запросом '{query}' и категориями {categories}"
        )

    def test_retriever_respects_category_filter(self, retriever):
        """Retriever должен фильтровать по категориям."""
        # Ищем в pricing
        results_pricing = retriever.search("стоимость", categories=["pricing"])

        # Ищем в equipment
        results_equipment = retriever.search("сканер", categories=["equipment"])

        # Проверяем что результаты из правильных категорий
        if results_pricing:
            assert all(r.section.category == "pricing" for r in results_pricing), (
                "Результаты должны быть только из категории 'pricing'"
            )

        if results_equipment:
            assert all(r.section.category == "equipment" for r in results_equipment), (
                "Результаты должны быть только из категории 'equipment'"
            )


class TestCategoryConsistency:
    """Тесты консистентности категорий."""

    def test_no_typos_in_category_names(self):
        """Проверяем что нет опечаток в названиях категорий."""
        valid_categories = {
            "equipment", "products", "pricing", "support", "tis",
            "regions", "features", "inventory", "integrations",
            "analytics", "employees", "stability", "fiscal",
            "mobile", "promotions", "competitors", "faq"
        }

        for intent, categories in INTENT_TO_CATEGORY.items():
            for cat in categories:
                assert cat in valid_categories, (
                    f"Категория '{cat}' в интенте '{intent}' "
                    f"похожа на опечатку. Допустимые: {sorted(valid_categories)}"
                )

    def test_categories_are_lowercase(self):
        """Все категории должны быть в нижнем регистре."""
        for intent, categories in INTENT_TO_CATEGORY.items():
            for cat in categories:
                assert cat == cat.lower(), (
                    f"Категория '{cat}' в интенте '{intent}' "
                    f"должна быть в нижнем регистре"
                )

    def test_no_duplicate_categories_per_intent(self):
        """Не должно быть дублирующихся категорий для одного интента."""
        for intent, categories in INTENT_TO_CATEGORY.items():
            unique_cats = set(categories)
            assert len(categories) == len(unique_cats), (
                f"Интент '{intent}' имеет дублирующиеся категории: {categories}"
            )
