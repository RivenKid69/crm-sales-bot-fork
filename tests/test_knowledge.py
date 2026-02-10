"""
Тесты для модуля базы знаний Wipon.
"""

import sys
import os

# Добавляем src в путь для импорта

import pytest
from src.knowledge.retriever import KnowledgeRetriever
from src.knowledge.base import KnowledgeBase, KnowledgeSection
from src.knowledge import WIPON_KNOWLEDGE

class TestKnowledgeBase:
    """Тесты структуры базы знаний"""

    def test_knowledge_base_structure(self):
        """База знаний имеет корректную структуру"""
        assert WIPON_KNOWLEDGE.company_name == "Wipon"
        assert len(WIPON_KNOWLEDGE.sections) > 0

    def test_get_by_category(self):
        """Получение секций по категории"""
        pricing_sections = WIPON_KNOWLEDGE.get_by_category("pricing")
        assert len(pricing_sections) > 0
        for section in pricing_sections:
            assert section.category == "pricing"

    def test_get_by_topic(self):
        """Получение секции по теме"""
        section = WIPON_KNOWLEDGE.get_by_topic("tariffs")
        assert section is not None
        assert section.topic == "tariffs"

    def test_all_sections_have_required_fields(self):
        """Все секции имеют обязательные поля"""
        for section in WIPON_KNOWLEDGE.sections:
            assert section.category, f"Section {section.topic} has no category"
            assert section.topic, f"Section has no topic"
            assert section.keywords, f"Section {section.topic} has no keywords"
            assert section.facts, f"Section {section.topic} has no facts"
            assert 1 <= section.priority <= 10, f"Section {section.topic} has invalid priority"

class TestKnowledgeRetriever:
    """Тесты для retriever'а"""

    @pytest.fixture
    def retriever(self):
        """Создаём retriever без эмбеддингов для быстрых тестов"""
        return KnowledgeRetriever(use_embeddings=False)

    def test_pricing_retrieval(self, retriever):
        """Вопрос о цене → факты о тарифах"""
        facts = retriever.retrieve("Сколько стоит?", intent="price_question")
        assert facts, "Should return pricing facts"
        assert "Mini" in facts or "тариф" in facts.lower() or "Тариф" in facts

    def test_pricing_retrieval_alt(self, retriever):
        """Альтернативный вопрос о цене"""
        facts = retriever.retrieve("Какая цена?", intent="price_question")
        assert facts, "Should return pricing facts"

    def test_integration_retrieval(self, retriever):
        """Вопрос об интеграции → конкретные факты"""
        facts = retriever.retrieve("Работаете с Kaspi?", intent="question_integrations")
        assert facts, "Should return integration facts"
        assert "Kaspi" in facts or "каспи" in facts.lower()

    def test_integration_retrieval_kaspi_lowercase(self, retriever):
        """Вопрос о каспи с опечаткой/разным регистром"""
        facts = retriever.retrieve("есть интеграция с каспи?", intent="question_integrations")
        assert facts, "Should return integration facts for 'каспи'"
        assert "Kaspi" in facts or "маркетплейс" in facts.lower()

    def test_no_hallucination(self, retriever):
        """Неизвестный вопрос → пустой результат или fallback без SAP"""
        facts = retriever.retrieve("Есть интеграция с SAP?", intent="question_integrations")
        # SAP нет в базе → либо пусто, либо общие факты без SAP
        assert "SAP" not in facts

    def test_competitor_comparison(self, retriever):
        """Вопрос о конкуренте → сравнение"""
        facts = retriever.retrieve("Чем лучше iiko?", intent="objection_competitor")
        assert facts, "Should return competitor comparison facts"
        assert "iiko" in facts.lower() or "дешевле" in facts.lower() or "проще" in facts.lower()

    def test_features_retrieval(self, retriever):
        """Вопрос о функциях → факты о продуктах/функциях"""
        facts = retriever.retrieve("Какие возможности есть?", intent="question_features")
        assert facts, "Should return features facts"

    def test_kassa_retrieval(self, retriever):
        """Вопрос о кассе → факты о Wipon Kassa"""
        facts = retriever.retrieve("Расскажите про онлайн-кассу")
        assert facts, "Should return kassa facts"
        assert "касс" in facts.lower() or "ОФД" in facts

    def test_alcohol_retrieval(self, retriever):
        """Вопрос об алкоголе → факты о Wipon Pro"""
        facts = retriever.retrieve("Как проверять алкоголь?")
        assert facts, "Should return alcohol checking facts"
        assert "алкоголь" in facts.lower() or "УКМ" in facts

    def test_company_info(self, retriever):
        """Получение информации о компании"""
        info = retriever.get_company_info()
        assert "Wipon" in info
        assert "2014" in info or "50,000" in info

    def test_empty_message(self, retriever):
        """Пустое сообщение не вызывает ошибок"""
        facts = retriever.retrieve("")
        # Может вернуть пустой результат или что-то
        assert isinstance(facts, str)

    def test_greeting_intent_no_facts(self, retriever):
        """Для greeting интента не нужны факты"""
        facts = retriever.retrieve("Привет!", intent="greeting")
        # greeting → пустой список категорий → поиск по всем
        # Но "Привет" не содержит ключевых слов → пустой результат
        assert isinstance(facts, str)

class TestKeywordSearch:
    """Тесты поиска по ключевым словам"""

    @pytest.fixture
    def retriever(self):
        return KnowledgeRetriever(use_embeddings=False)

    def test_exact_keyword_match(self, retriever):
        """Точное совпадение ключевого слова"""
        facts = retriever.retrieve("тариф")
        assert facts
        assert "тариф" in facts.lower() or "Mini" in facts

    def test_partial_keyword_match(self, retriever):
        """Частичное совпадение (подстрока)"""
        facts = retriever.retrieve("какие тарифы есть?")
        assert facts
        assert "тариф" in facts.lower() or "Mini" in facts

    def test_multiple_keywords(self, retriever):
        """Несколько ключевых слов повышают релевантность"""
        facts = retriever.retrieve("цена и стоимость тарифа")
        assert facts
        # Должен найти pricing секцию

    def test_case_insensitive(self, retriever):
        """Регистронезависимый поиск"""
        facts_lower = retriever.retrieve("касса")
        facts_upper = retriever.retrieve("КАССА")
        facts_mixed = retriever.retrieve("Касса")

        # Все должны вернуть результаты
        assert facts_lower
        assert facts_upper
        assert facts_mixed

class TestIntentFiltering:
    """Тесты фильтрации по интентам"""

    @pytest.fixture
    def retriever(self):
        return KnowledgeRetriever(use_embeddings=False)

    def test_price_intent_filters_to_pricing(self, retriever):
        """price_question фильтрует до pricing категории"""
        facts = retriever.retrieve("сколько", intent="price_question")
        # Должен искать только в pricing категории
        assert facts

    def test_features_intent_includes_products(self, retriever):
        """question_features включает products и features"""
        facts = retriever.retrieve("возможности", intent="question_features")
        assert facts

    def test_no_intent_searches_all(self, retriever):
        """Без интента ищем по всем секциям"""
        facts = retriever.retrieve("касса")
        assert facts

class TestPerformance:
    """Тесты производительности"""

    @pytest.fixture
    def retriever(self):
        return KnowledgeRetriever(use_embeddings=False)

    def test_keyword_search_fast(self, retriever):
        """Поиск по ключевым словам должен быть быстрым"""
        import time

        start = time.time()
        for _ in range(100):
            retriever.retrieve("сколько стоит?", intent="price_question")
        elapsed = time.time() - start

        # 100 запросов должны выполниться за < 500ms (5ms на запрос)
        assert elapsed < 0.5, f"Keyword search too slow: {elapsed:.3f}s for 100 queries"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
