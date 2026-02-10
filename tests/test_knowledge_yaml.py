"""
Тесты для YAML базы знаний.
"""

import pytest
from pathlib import Path
import sys

from src.knowledge import WIPON_KNOWLEDGE, load_knowledge_base, KnowledgeSection

class TestKnowledgeLoading:
    """Тесты загрузки базы знаний"""

    def test_load_returns_knowledge_base(self):
        """Проверка что загрузка возвращает KnowledgeBase"""
        kb = load_knowledge_base()
        assert kb is not None
        assert hasattr(kb, "sections")
        assert hasattr(kb, "company_name")

    def test_sections_count(self):
        """Проверка количества секций (минимум 1700 после расширения базы знаний)"""
        kb = load_knowledge_base()
        assert len(kb.sections) >= 1700, f"Ожидалось >= 1700, получено {len(kb.sections)}"

    def test_all_sections_are_knowledge_section(self):
        """Проверка типов секций"""
        kb = load_knowledge_base()
        for section in kb.sections:
            assert isinstance(section, KnowledgeSection)

    def test_company_info(self):
        """Проверка информации о компании"""
        kb = load_knowledge_base()
        assert kb.company_name == "Wipon"
        assert "Казахстан" in kb.company_description

class TestKnowledgeContent:
    """Тесты содержимого"""

    def test_all_topics_unique(self):
        """Проверка уникальности topics"""
        kb = load_knowledge_base()
        topics = [s.topic for s in kb.sections]
        assert len(topics) == len(set(topics)), "Есть дублирующиеся topics"

    def test_all_sections_have_required_fields(self):
        """Проверка обязательных полей"""
        kb = load_knowledge_base()
        for section in kb.sections:
            assert section.category, f"Пустая category в {section.topic}"
            assert section.topic, "Пустой topic"
            assert section.keywords, f"Пустые keywords в {section.topic}"
            assert section.facts, f"Пустые facts в {section.topic}"
            assert 1 <= section.priority <= 10, f"priority вне диапазона в {section.topic}"

    def test_categories_distribution(self):
        """Проверка распределения по категориям"""
        kb = load_knowledge_base()
        categories = {}
        for s in kb.sections:
            categories[s.category] = categories.get(s.category, 0) + 1

        # Проверить основные категории
        assert categories.get("tis", 0) >= 130, "Мало секций tis"
        assert categories.get("support", 0) >= 60, "Мало секций support"
        assert categories.get("products", 0) >= 10, "Мало секций products"

    @pytest.mark.parametrize("topic,expected_category", [
        ("wipon_kassa", "products"),
        ("wipon_pro", "products"),
        ("overview", "products"),
    ])
    def test_specific_topics_exist(self, topic, expected_category):
        """Проверка существования ключевых секций"""
        kb = load_knowledge_base()
        section = kb.get_by_topic(topic)
        assert section is not None, f"Секция {topic} не найдена"
        assert section.category == expected_category

class TestKnowledgeAPI:
    """Тесты API"""

    def test_get_by_category(self):
        """Тест get_by_category"""
        kb = load_knowledge_base()

        pricing = kb.get_by_category("pricing")
        assert len(pricing) >= 100, f"Ожидалось >= 100 секций pricing, получено {len(pricing)}"
        assert all(s.category == "pricing" for s in pricing)

    def test_get_by_category_empty(self):
        """Тест get_by_category для несуществующей категории"""
        kb = load_knowledge_base()
        result = kb.get_by_category("nonexistent")
        assert result == []

    def test_get_by_topic(self):
        """Тест get_by_topic"""
        kb = load_knowledge_base()

        section = kb.get_by_topic("wipon_kassa")
        assert section is not None
        assert section.topic == "wipon_kassa"
        assert "касса" in section.keywords or "Касса" in section.facts

    def test_get_by_topic_none(self):
        """Тест get_by_topic для несуществующего topic"""
        kb = load_knowledge_base()
        result = kb.get_by_topic("nonexistent_topic_12345")
        assert result is None

class TestBackwardsCompatibility:
    """Тесты обратной совместимости"""

    def test_global_import(self):
        """Проверка глобального импорта"""
        from src.knowledge import WIPON_KNOWLEDGE
        assert WIPON_KNOWLEDGE is not None

    def test_global_sections(self):
        """Проверка доступа к sections (минимум 1700 после расширения)"""
        assert len(WIPON_KNOWLEDGE.sections) >= 1700

    def test_global_methods(self):
        """Проверка методов глобального объекта"""
        pricing = WIPON_KNOWLEDGE.get_by_category("pricing")
        assert len(pricing) > 0

        kassa = WIPON_KNOWLEDGE.get_by_topic("wipon_kassa")
        assert kassa is not None

class TestYAMLFiles:
    """Тесты YAML файлов"""

    def test_yaml_files_exist(self):
        """Проверка существования YAML файлов"""
        data_dir = Path(__file__).parent.parent / "src" / "knowledge" / "data"
        assert data_dir.exists(), f"Директория {data_dir} не существует"

        yaml_files = list(data_dir.glob("*.yaml"))
        assert len(yaml_files) > 0, "Нет YAML файлов"

    def test_meta_file_exists(self):
        """Проверка файла метаданных"""
        data_dir = Path(__file__).parent.parent / "src" / "knowledge" / "data"
        meta_file = data_dir / "_meta.yaml"
        assert meta_file.exists(), "Файл _meta.yaml не существует"

    def test_all_categories_have_files(self):
        """Проверка что все основные категории имеют файлы"""
        data_dir = Path(__file__).parent.parent / "src" / "knowledge" / "data"

        expected_files = [
            "products.yaml",
            "pricing.yaml",
            "integrations.yaml",
            "support.yaml",
            "tis.yaml",
            "equipment.yaml",
        ]

        for filename in expected_files:
            filepath = data_dir / filename
            assert filepath.exists(), f"Файл {filename} не существует"
