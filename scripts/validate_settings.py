#!/usr/bin/env python3
"""
Валидация settings.yaml и проверка что всё работает.

Запуск: python3 scripts/validate_settings.py
"""

import sys
from pathlib import Path

# Добавляем src в путь
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.settings import load_settings, validate_settings, DEFAULTS


def compare_with_defaults(settings, defaults, path=""):
    """Сравнить настройки с defaults, показать что переопределено"""
    overrides = []

    for key, default_value in defaults.items():
        current_path = f"{path}.{key}" if path else key

        if isinstance(default_value, dict):
            if key in settings:
                overrides.extend(compare_with_defaults(settings[key], default_value, current_path))
        else:
            if key in settings and settings[key] != default_value:
                overrides.append((current_path, default_value, settings[key]))

    return overrides


def test_imports():
    """Проверить что все импорты работают"""
    print("\n1. Проверка импортов...")

    try:
        from src.settings import settings
        print("   [+] from settings import settings")

        from src.llm import OllamaLLM
        print("   [+] from llm import OllamaLLM")

        from src.knowledge.retriever import CascadeRetriever
        print("   [+] from knowledge.retriever import CascadeRetriever")

        from src.generator import ResponseGenerator
        print("   [+] from generator import ResponseGenerator")

        from src.config import CLASSIFIER_CONFIG
        print("   [+] from config import CLASSIFIER_CONFIG")

        return True
    except Exception as e:
        print(f"   [-] Ошибка импорта: {e}")
        return False


def test_settings_access():
    """Проверить доступ к настройкам"""
    print("\n2. Проверка доступа к настройкам...")

    from src.settings import settings

    tests = [
        ("settings.llm.model", settings.llm.model),
        ("settings.llm.base_url", settings.llm.base_url),
        ("settings.llm.timeout", settings.llm.timeout),
        ("settings.retriever.thresholds.exact", settings.retriever.thresholds.exact),
        ("settings.retriever.thresholds.lemma", settings.retriever.thresholds.lemma),
        ("settings.generator.max_retries", settings.generator.max_retries),
        ("settings.classifier.weights.root_match", settings.classifier.weights.root_match),
    ]

    all_ok = True
    for path, value in tests:
        if value is not None:
            print(f"   [+] {path} = {value}")
        else:
            print(f"   [-] {path} = None (ошибка!)")
            all_ok = False

    return all_ok


def test_llm_initialization():
    """Проверить инициализацию LLM"""
    print("\n3. Проверка инициализации LLM...")

    from src.llm import OllamaLLM
    from src.settings import settings

    llm = OllamaLLM()

    if llm.model == settings.llm.model:
        print(f"   [+] model = {llm.model}")
    else:
        print(f"   [-] model mismatch: {llm.model} != {settings.llm.model}")
        return False

    if llm.base_url == settings.llm.base_url:
        print(f"   [+] base_url = {llm.base_url}")
    else:
        print(f"   [-] base_url mismatch")
        return False

    if llm.timeout == settings.llm.timeout:
        print(f"   [+] timeout = {llm.timeout}")
    else:
        print(f"   [-] timeout mismatch")
        return False

    return True


def test_retriever_initialization():
    """Проверить инициализацию Retriever"""
    print("\n4. Проверка инициализации Retriever...")

    try:
        from src.knowledge.retriever import CascadeRetriever
        from src.settings import settings

        # Создаём retriever без эмбеддингов для быстроты
        retriever = CascadeRetriever(use_embeddings=False)

        checks = [
            ("exact_threshold", retriever.exact_threshold, settings.retriever.thresholds.exact),
            ("lemma_threshold", retriever.lemma_threshold, settings.retriever.thresholds.lemma),
            ("semantic_threshold", retriever.semantic_threshold, settings.retriever.thresholds.semantic),
        ]

        all_ok = True
        for name, actual, expected in checks:
            if actual == expected:
                print(f"   [+] {name} = {actual}")
            else:
                print(f"   [-] {name}: {actual} != {expected}")
                all_ok = False

        return all_ok
    except Exception as e:
        print(f"   [-] Ошибка: {e}")
        return False


def test_generator_initialization():
    """Проверить инициализацию Generator"""
    print("\n5. Проверка инициализации Generator...")

    try:
        from src.generator import ResponseGenerator
        from src.settings import settings

        # Создаём mock LLM
        class MockLLM:
            def generate(self, prompt):
                return "Mock response"

        gen = ResponseGenerator(MockLLM())

        checks = [
            ("max_retries", gen.max_retries, settings.generator.max_retries),
            ("history_length", gen.history_length, settings.generator.history_length),
            ("retriever_top_k", gen.retriever_top_k, settings.generator.retriever_top_k),
        ]

        all_ok = True
        for name, actual, expected in checks:
            if actual == expected:
                print(f"   [+] {name} = {actual}")
            else:
                print(f"   [-] {name}: {actual} != {expected}")
                all_ok = False

        # Проверяем allowed_english
        expected_words = set(settings.generator.allowed_english_words)
        if gen.allowed_english == expected_words:
            print(f"   [+] allowed_english = {len(gen.allowed_english)} words")
        else:
            print(f"   [-] allowed_english mismatch")
            all_ok = False

        return all_ok
    except Exception as e:
        print(f"   [-] Ошибка: {e}")
        return False


def test_classifier_config():
    """Проверить CLASSIFIER_CONFIG"""
    print("\n6. Проверка CLASSIFIER_CONFIG...")

    try:
        from src.config import CLASSIFIER_CONFIG
        from src.settings import settings

        checks = [
            ("root_match_weight", CLASSIFIER_CONFIG["root_match_weight"], settings.classifier.weights.root_match),
            ("phrase_match_weight", CLASSIFIER_CONFIG["phrase_match_weight"], settings.classifier.weights.phrase_match),
            ("lemma_match_weight", CLASSIFIER_CONFIG["lemma_match_weight"], settings.classifier.weights.lemma_match),
            ("high_confidence_threshold", CLASSIFIER_CONFIG["high_confidence_threshold"], settings.classifier.thresholds.high_confidence),
            ("min_confidence", CLASSIFIER_CONFIG["min_confidence"], settings.classifier.thresholds.min_confidence),
        ]

        all_ok = True
        for name, actual, expected in checks:
            if actual == expected:
                print(f"   [+] {name} = {actual}")
            else:
                print(f"   [-] {name}: {actual} != {expected}")
                all_ok = False

        return all_ok
    except Exception as e:
        print(f"   [-] Ошибка: {e}")
        return False


def test_override_in_constructor():
    """Проверить переопределение параметров в конструкторе"""
    print("\n7. Проверка переопределения в конструкторе...")

    try:
        from src.llm import OllamaLLM

        llm = OllamaLLM(model="custom-model", timeout=999)

        if llm.model == "custom-model":
            print(f"   [+] model override = {llm.model}")
        else:
            print(f"   [-] model override failed")
            return False

        if llm.timeout == 999:
            print(f"   [+] timeout override = {llm.timeout}")
        else:
            print(f"   [-] timeout override failed")
            return False

        return True
    except Exception as e:
        print(f"   [-] Ошибка: {e}")
        return False


def main():
    print("=" * 60)
    print("ВАЛИДАЦИЯ SETTINGS.YAML")
    print("=" * 60)

    # Загрузка и базовая валидация
    print("\n0. Загрузка настроек...")
    settings = load_settings()
    errors = validate_settings(settings)

    if errors:
        print("   [-] Найдены ошибки:")
        for err in errors:
            print(f"      - {err}")
        sys.exit(1)
    else:
        print("   [+] Базовая валидация пройдена")

    # Показать что переопределено
    overrides = compare_with_defaults(dict(settings), DEFAULTS)
    if overrides:
        print("\n   Переопределённые значения:")
        for path, default, current in overrides:
            print(f"      {path}: {default} -> {current}")

    # Тесты
    results = []
    results.append(("Импорты", test_imports()))
    results.append(("Доступ к настройкам", test_settings_access()))
    results.append(("LLM инициализация", test_llm_initialization()))
    results.append(("Retriever инициализация", test_retriever_initialization()))
    results.append(("Generator инициализация", test_generator_initialization()))
    results.append(("CLASSIFIER_CONFIG", test_classifier_config()))
    results.append(("Переопределение в конструкторе", test_override_in_constructor()))

    # Итоги
    print("\n" + "=" * 60)
    print("ИТОГИ")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "[+]" if passed else "[-]"
        print(f"   {status} {name}")
        if not passed:
            all_passed = False

    if all_passed:
        print("\n[+] ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
        return 0
    else:
        print("\n[-] ЕСТЬ ОШИБКИ")
        return 1


if __name__ == "__main__":
    sys.exit(main())
