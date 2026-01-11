"""
Загрузчик базы знаний из YAML файлов.

Использование:
    from knowledge.loader import load_knowledge_base
    kb = load_knowledge_base()
"""

import yaml
from pathlib import Path
from typing import List
from .base import KnowledgeBase, KnowledgeSection

# Путь к директории с YAML файлами
DATA_DIR = Path(__file__).parent / "data"

# Маппинг файл → категория (для файлов где category не указан явно)
FILE_TO_CATEGORY = {
    "products.yaml": "products",
    "pricing.yaml": "pricing",
    "integrations.yaml": "integrations",
    "support.yaml": "support",
    "tis.yaml": "tis",
    "equipment.yaml": "equipment",
    "analytics.yaml": "analytics",
    "inventory.yaml": "inventory",
    "employees.yaml": "employees",
    "stability.yaml": "stability",
    "promotions.yaml": "promotions",
    "fiscal.yaml": "fiscal",
    "mobile.yaml": "mobile",
    "features.yaml": "features",
    "faq.yaml": "faq",
    "regions.yaml": "regions",
    "competitors.yaml": "competitors",
}


def _load_yaml(filepath: Path) -> dict:
    """Загрузить YAML файл"""
    with open(filepath, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_sections_from_file(filepath: Path) -> List[KnowledgeSection]:
    """Загрузить секции из одного YAML файла"""
    data = _load_yaml(filepath)
    if not data or "sections" not in data:
        return []

    filename = filepath.name
    default_category = FILE_TO_CATEGORY.get(filename)

    sections = []
    for item in data["sections"]:
        # Категория: из секции или из имени файла
        category = item.get("category", default_category)
        if not category:
            raise ValueError(f"Не указана категория для секции {item.get('topic')} в {filename}")

        section = KnowledgeSection(
            category=category,
            topic=item["topic"],
            keywords=item["keywords"],
            facts=item["facts"],
            priority=item.get("priority", 5),
        )
        sections.append(section)

    return sections


def load_knowledge_base() -> KnowledgeBase:
    """
    Загрузить базу знаний из YAML файлов.

    Returns:
        KnowledgeBase с всеми секциями
    """
    # Загрузить метаданные
    meta_path = DATA_DIR / "_meta.yaml"
    if not meta_path.exists():
        raise FileNotFoundError(f"Не найден файл метаданных: {meta_path}")

    meta = _load_yaml(meta_path)
    company_name = meta["company"]["name"]
    company_description = meta["company"]["description"]
    expected_total = meta["stats"]["total_sections"]

    # Загрузить все секции
    all_sections: List[KnowledgeSection] = []

    for yaml_file in sorted(DATA_DIR.glob("*.yaml")):
        if yaml_file.name == "_meta.yaml":
            continue

        sections = _load_sections_from_file(yaml_file)
        all_sections.extend(sections)

    # Проверка количества
    if len(all_sections) != expected_total:
        raise ValueError(
            f"Несоответствие количества секций: "
            f"ожидалось {expected_total}, загружено {len(all_sections)}"
        )

    # Проверка уникальности topics
    topics = [s.topic for s in all_sections]
    if len(topics) != len(set(topics)):
        duplicates = [t for t in topics if topics.count(t) > 1]
        raise ValueError(f"Дублирующиеся topics: {set(duplicates)}")

    return KnowledgeBase(
        company_name=company_name,
        company_description=company_description,
        sections=all_sections,
    )


# Для обратной совместимости
def get_knowledge() -> KnowledgeBase:
    """Alias для load_knowledge_base()"""
    return load_knowledge_base()
