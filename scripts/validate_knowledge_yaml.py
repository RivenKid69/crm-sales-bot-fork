"""
Валидация YAML базы знаний.
Проверяет что все данные корректно загружаются и соответствуют оригиналу.

Запуск: python scripts/validate_knowledge_yaml.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.knowledge.loader import load_knowledge_base
from src.knowledge.base import KnowledgeSection

# Импорт ОРИГИНАЛЬНЫХ данных для сравнения
# ВАЖНО: Этот импорт работает только пока data.py не удалён!
try:
    from src.knowledge.data import WIPON_KNOWLEDGE as ORIGINAL_KB
    HAS_ORIGINAL = True
except ImportError:
    HAS_ORIGINAL = False
    print("Warning: Оригинальный data.py не найден, сравнение невозможно")


def validate_structure():
    """Проверка что YAML загружается без ошибок"""
    print("\n1. Проверка загрузки YAML...")
    try:
        kb = load_knowledge_base()
        print(f"   OK Загружено {len(kb.sections)} секций")
        print(f"   OK Компания: {kb.company_name}")
        return kb
    except Exception as e:
        print(f"   FAIL ОШИБКА: {e}")
        sys.exit(1)


def validate_count(yaml_kb):
    """Проверка количества секций"""
    print("\n2. Проверка количества секций...")

    if HAS_ORIGINAL:
        original_count = len(ORIGINAL_KB.sections)
        yaml_count = len(yaml_kb.sections)

        if original_count == yaml_count:
            print(f"   OK Количество совпадает: {yaml_count}")
        else:
            print(f"   FAIL ОШИБКА: Оригинал={original_count}, YAML={yaml_count}")
            print(f"   FAIL Потеряно: {original_count - yaml_count} секций")
            sys.exit(1)
    else:
        print(f"   WARN Сравнение невозможно, загружено: {len(yaml_kb.sections)}")


def validate_topics(yaml_kb):
    """Проверка уникальности и соответствия topics"""
    print("\n3. Проверка topics...")

    yaml_topics = {s.topic for s in yaml_kb.sections}

    # Проверка уникальности
    if len(yaml_topics) != len(yaml_kb.sections):
        print("   FAIL ОШИБКА: Есть дублирующиеся topics!")
        topics_list = [s.topic for s in yaml_kb.sections]
        duplicates = [t for t in topics_list if topics_list.count(t) > 1]
        print(f"   FAIL Дубликаты: {set(duplicates)}")
        sys.exit(1)

    print(f"   OK Все {len(yaml_topics)} topics уникальны")

    if HAS_ORIGINAL:
        original_topics = {s.topic for s in ORIGINAL_KB.sections}

        missing = original_topics - yaml_topics
        extra = yaml_topics - original_topics

        if missing:
            print(f"   FAIL ОШИБКА: Отсутствуют topics: {missing}")
            sys.exit(1)
        if extra:
            print(f"   FAIL ОШИБКА: Лишние topics: {extra}")
            sys.exit(1)

        print("   OK Все topics совпадают с оригиналом")


def validate_content(yaml_kb):
    """Проверка содержимого секций"""
    print("\n4. Проверка содержимого секций...")

    if not HAS_ORIGINAL:
        print("   WARN Сравнение невозможно без оригинала")
        return

    # Создать словарь оригинальных секций по topic
    original_by_topic = {s.topic: s for s in ORIGINAL_KB.sections}

    errors = []

    for yaml_section in yaml_kb.sections:
        original = original_by_topic.get(yaml_section.topic)
        if not original:
            errors.append(f"Topic '{yaml_section.topic}' не найден в оригинале")
            continue

        # Проверка category
        if yaml_section.category != original.category:
            errors.append(
                f"[{yaml_section.topic}] category: '{yaml_section.category}' != '{original.category}'"
            )

        # Проверка priority
        if yaml_section.priority != original.priority:
            errors.append(
                f"[{yaml_section.topic}] priority: {yaml_section.priority} != {original.priority}"
            )

        # Проверка keywords (как множества, порядок не важен)
        yaml_kw = set(yaml_section.keywords)
        orig_kw = set(original.keywords)

        if yaml_kw != orig_kw:
            missing_kw = orig_kw - yaml_kw
            extra_kw = yaml_kw - orig_kw
            if missing_kw:
                errors.append(f"[{yaml_section.topic}] Отсутствуют keywords: {missing_kw}")
            if extra_kw:
                errors.append(f"[{yaml_section.topic}] Лишние keywords: {extra_kw}")

        # Проверка facts (нормализованное сравнение)
        yaml_facts = yaml_section.facts.strip()
        orig_facts = original.facts.strip()

        if yaml_facts != orig_facts:
            # Детальное сравнение
            yaml_normalized = yaml_facts.replace("\r\n", "\n")
            orig_normalized = orig_facts.replace("\r\n", "\n")

            if yaml_normalized != orig_normalized:
                # Найти первое различие
                for i, (c1, c2) in enumerate(zip(yaml_normalized, orig_normalized)):
                    if c1 != c2:
                        errors.append(
                            f"[{yaml_section.topic}] facts различаются на позиции {i}: "
                            f"'{yaml_normalized[max(0,i-10):i+10]}' vs '{orig_normalized[max(0,i-10):i+10]}'"
                        )
                        break
                else:
                    if len(yaml_normalized) != len(orig_normalized):
                        errors.append(
                            f"[{yaml_section.topic}] facts разной длины: "
                            f"{len(yaml_normalized)} vs {len(orig_normalized)}"
                        )

    if errors:
        print(f"   FAIL Найдено {len(errors)} ошибок:")
        for err in errors[:20]:  # Показать первые 20
            print(f"      - {err}")
        if len(errors) > 20:
            print(f"      ... и ещё {len(errors) - 20} ошибок")
        sys.exit(1)

    print("   OK Всё содержимое совпадает с оригиналом")


def validate_api_compatibility(yaml_kb):
    """Проверка обратной совместимости API"""
    print("\n5. Проверка API совместимости...")

    # Тест get_by_category
    pricing = yaml_kb.get_by_category("pricing")
    if not pricing:
        print("   FAIL ОШИБКА: get_by_category('pricing') вернул пустой список")
        sys.exit(1)
    print(f"   OK get_by_category('pricing'): {len(pricing)} секций")

    # Тест get_by_topic
    kassa = yaml_kb.get_by_topic("wipon_kassa")
    if not kassa:
        print("   FAIL ОШИБКА: get_by_topic('wipon_kassa') вернул None")
        sys.exit(1)
    print(f"   OK get_by_topic('wipon_kassa'): {kassa.topic}")

    # Тест атрибутов
    assert yaml_kb.company_name, "company_name пустой"
    assert yaml_kb.company_description, "company_description пустой"
    assert yaml_kb.sections, "sections пустой"
    print("   OK Все атрибуты доступны")


def validate_import_compatibility():
    """Проверка что импорт работает как раньше"""
    print("\n6. Проверка импорта...")

    try:
        from src.knowledge import WIPON_KNOWLEDGE

        # Проверить что это работает
        _ = WIPON_KNOWLEDGE.company_name
        _ = WIPON_KNOWLEDGE.sections
        _ = WIPON_KNOWLEDGE.get_by_category("products")
        _ = WIPON_KNOWLEDGE.get_by_topic("overview")

        print("   OK from knowledge import WIPON_KNOWLEDGE работает")
    except Exception as e:
        print(f"   FAIL ОШИБКА импорта: {e}")
        sys.exit(1)


def main():
    print("=" * 60)
    print("ВАЛИДАЦИЯ YAML БАЗЫ ЗНАНИЙ")
    print("=" * 60)

    yaml_kb = validate_structure()
    validate_count(yaml_kb)
    validate_topics(yaml_kb)
    validate_content(yaml_kb)
    validate_api_compatibility(yaml_kb)
    validate_import_compatibility()

    print("\n" + "=" * 60)
    print("OK ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    print("=" * 60)


if __name__ == "__main__":
    main()
