"""
Статический валидатор для проверки соблюдения SSOT принципа для ценовых данных.

Проверяет:
1. Отсутствие hardcoded цен в Python коде
2. Отсутствие рублевых цен в YAML конфигурации
3. Все цены только в тенге (₸)
"""

import re
from pathlib import Path
from typing import List, Tuple

# Паттерны для поиска нарушений
PATTERNS = {
    "ruble_symbol": r"₽",
    "ruble_word": r"\b(рубл|рубля|рублей)\b",
    "hardcoded_prices": r"\b(590|790|990)\b.*?(чел|мес|год)",
    "discount_hardcode": r"discount.*?20",
}

def validate_file(file_path: Path) -> List[Tuple[int, str, str]]:
    """
    Валидировать файл на наличие hardcoded цен.

    Returns:
        List[(line_number, pattern_name, line_content)]
    """
    violations = []

    with open(file_path, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f, start=1):
            for pattern_name, pattern in PATTERNS.items():
                if re.search(pattern, line, re.IGNORECASE):
                    violations.append((i, pattern_name, line.strip()))

    return violations

def validate_codebase(root_dir: Path = Path("src")) -> bool:
    """Валидировать всю кодовую базу."""
    all_violations = {}

    # Проверяем Python файлы
    for py_file in root_dir.rglob("*.py"):
        violations = validate_file(py_file)
        if violations:
            all_violations[py_file] = violations

    # Проверяем YAML файлы (только prompts)
    yaml_dir = Path("src/yaml_config/templates")
    for yaml_file in yaml_dir.rglob("prompts.yaml"):
        violations = validate_file(yaml_file)
        if violations:
            all_violations[yaml_file] = violations

    # Выводим отчет
    if all_violations:
        print("SSOT Validation FAILED\n")
        for file_path, violations in all_violations.items():
            print(f"File: {file_path}")
            for line_num, pattern, content in violations:
                print(f"  Line {line_num} [{pattern}]: {content}")
            print()
        return False
    else:
        print("SSOT Validation PASSED")
        return True

if __name__ == "__main__":
    import sys
    success = validate_codebase()
    sys.exit(0 if success else 1)
