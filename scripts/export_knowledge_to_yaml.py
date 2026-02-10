"""
Экспорт базы знаний из data.py в YAML файлы.
Запуск: python scripts/export_knowledge_to_yaml.py
"""

import yaml
import os
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any
from datetime import date

# Добавить src в path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.knowledge.data import WIPON_KNOWLEDGE
from src.knowledge.base import KnowledgeSection

# Директория для YAML файлов
OUTPUT_DIR = Path(__file__).parent.parent / "src" / "knowledge" / "data"


class LiteralScalarString(str):
    """Класс для сохранения многострочных строк в YAML с |"""
    pass


def literal_representer(dumper, data):
    """Представление многострочных строк с |"""
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')


yaml.add_representer(LiteralScalarString, literal_representer)


def section_to_dict(section: KnowledgeSection) -> Dict[str, Any]:
    """Конвертировать секцию в словарь для YAML"""
    facts = section.facts.strip()
    return {
        "topic": section.topic,
        "priority": section.priority,
        "keywords": list(section.keywords),
        "facts": LiteralScalarString(facts),
    }


def export_meta(category_counts: Dict[str, int]):
    """Экспорт метаданных"""
    meta = {
        "company": {
            "name": WIPON_KNOWLEDGE.company_name,
            "description": WIPON_KNOWLEDGE.company_description,
        },
        "stats": {
            "total_sections": len(WIPON_KNOWLEDGE.sections),
            "last_updated": str(date.today()),
            "categories": [
                {"name": cat, "count": count}
                for cat, count in sorted(category_counts.items(), key=lambda x: -x[1])
            ]
        }
    }

    output_path = OUTPUT_DIR / "_meta.yaml"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Метаданные базы знаний Wipon\n")
        f.write("# Автоматически сгенерировано из data.py\n\n")
        yaml.dump(meta, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f"✓ Экспортировано: {output_path}")
    return meta


def export_category(category: str, sections: List[KnowledgeSection], filename: str) -> int:
    """Экспорт одной категории в YAML файл"""
    data = {
        "sections": [section_to_dict(s) for s in sections]
    }

    output_path = OUTPUT_DIR / filename
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# База знаний: {category}\n")
        f.write(f"# Категория: {category}\n")
        f.write(f"# Секций: {len(sections)}\n\n")
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False, width=1000)

    print(f"✓ Экспортировано: {output_path} ({len(sections)} секций)")
    return len(sections)


def export_other(sections_with_category: List[tuple]) -> int:
    """Экспорт мелких категорий в other.yaml (с сохранением category в каждой секции)"""
    data = {
        "sections": []
    }

    for category, section in sections_with_category:
        section_dict = section_to_dict(section)
        section_dict["category"] = category
        data["sections"].append(section_dict)

    output_path = OUTPUT_DIR / "other.yaml"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# База знаний: Прочие категории\n")
        f.write("# Категории с малым количеством секций\n")
        f.write(f"# Секций: {len(sections_with_category)}\n\n")
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False, width=1000)

    print(f"✓ Экспортировано: {output_path} ({len(sections_with_category)} секций)")
    return len(sections_with_category)


def main():
    # Создать директорию
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Группировка по категориям
    by_category: Dict[str, List[KnowledgeSection]] = defaultdict(list)
    for section in WIPON_KNOWLEDGE.sections:
        by_category[section.category].append(section)

    # Подсчёт для метаданных
    category_counts = {cat: len(sects) for cat, sects in by_category.items()}

    # Маппинг категория → файл
    # Крупные категории (>= 3 секций) — отдельные файлы
    CATEGORY_FILES = {
        "products": "products.yaml",
        "pricing": "pricing.yaml",
        "integrations": "integrations.yaml",
        "support": "support.yaml",
        "tis": "tis.yaml",
        "equipment": "equipment.yaml",
        "analytics": "analytics.yaml",
        "inventory": "inventory.yaml",
        "employees": "employees.yaml",
        "stability": "stability.yaml",
        "promotions": "promotions.yaml",
        "fiscal": "fiscal.yaml",
        "mobile": "mobile.yaml",
        "features": "features.yaml",
        "faq": "faq.yaml",
        "regions": "regions.yaml",
    }

    total_exported = 0
    other_sections = []

    # Экспорт метаданных
    export_meta(category_counts)

    # Экспорт по категориям
    for category, sections in by_category.items():
        if category in CATEGORY_FILES:
            count = export_category(category, sections, CATEGORY_FILES[category])
            total_exported += count
        else:
            # Мелкие категории → other.yaml
            for s in sections:
                other_sections.append((category, s))

    # Экспорт other.yaml
    if other_sections:
        count = export_other(other_sections)
        total_exported += count

    # Проверка
    expected = len(WIPON_KNOWLEDGE.sections)
    print(f"\n{'='*50}")
    print(f"Всего в data.py: {expected}")
    print(f"Всего экспортировано: {total_exported}")

    if total_exported == expected:
        print("✓ ВСЕ СЕКЦИИ ЭКСПОРТИРОВАНЫ")
    else:
        print(f"✗ ОШИБКА: Потеряно {expected - total_exported} секций!")
        sys.exit(1)


if __name__ == "__main__":
    main()
