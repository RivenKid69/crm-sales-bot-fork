"""
Загрузчик настроек из settings.yaml

Использование:
    from settings import settings

    model = settings.llm.model
    threshold = settings.retriever.thresholds.lemma
"""

import yaml
from pathlib import Path
from typing import List, Any


# Путь к файлу настроек
SETTINGS_FILE = Path(__file__).parent / "settings.yaml"

# Значения по умолчанию (используются если параметр не указан в YAML)
DEFAULTS = {
    "llm": {
        "model": "Qwen/Qwen3-4B-AWQ",
        "base_url": "http://localhost:8000/v1",
        "timeout": 60,
        "stream": False,
    },
    "retriever": {
        "use_embeddings": True,
        "embedder_model": "ai-forever/FRIDA",
        "thresholds": {
            "exact": 1.0,
            "lemma": 0.15,
            "semantic": 0.5,
        },
        "default_top_k": 2,
    },
    "generator": {
        "max_retries": 3,
        "history_length": 4,
        "retriever_top_k": 2,
        "allowed_english_words": [
            "crm", "api", "ok", "id", "ip", "sms",
            "email", "excel", "whatsapp", "telegram", "hr"
        ],
    },
    "classifier": {
        "weights": {
            "root_match": 1.0,
            "phrase_match": 2.0,
            "lemma_match": 1.5,
        },
        "thresholds": {
            "high_confidence": 0.7,
            "min_confidence": 0.3,
        },
    },
    "logging": {
        "level": "INFO",
        "log_llm_requests": False,
        "log_retriever_results": False,
    },
    "conditional_rules": {
        "enable_tracing": True,
        "log_level": "INFO",
        "log_context": False,
        "log_each_condition": False,
        "validate_on_startup": True,
        "coverage_threshold": 0.8,
    },
    "flow": {
        "active": "spin_selling",  # Default flow (can be overridden in settings.yaml)
    },
    "development": {
        "debug": False,
        "skip_embeddings": False,
    },
}


class DotDict(dict):
    """Словарь с доступом через точку: d.key вместо d['key']"""

    def __getattr__(self, key: str) -> Any:
        try:
            value = self[key]
            if isinstance(value, dict):
                return DotDict(value)
            return value
        except KeyError:
            raise AttributeError(f"Настройка '{key}' не найдена")

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value

    def get_nested(self, path: str, default: Any = None) -> Any:
        """Получить значение по пути: 'llm.model'"""
        keys = path.split('.')
        value = self
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value


def _deep_merge(base: dict, override: dict) -> dict:
    """Глубокое слияние словарей (override перезаписывает base)"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_settings(filepath: Path = None) -> DotDict:
    """
    Загрузить настройки из YAML файла.

    Порядок приоритета:
    1. Значения из YAML файла (высший приоритет)
    2. Значения по умолчанию (DEFAULTS)

    Args:
        filepath: Путь к файлу настроек (по умолчанию settings.yaml)

    Returns:
        DotDict с настройками
    """
    filepath = filepath or SETTINGS_FILE

    # Начинаем с defaults
    config = _deep_merge({}, DEFAULTS)  # Глубокая копия

    # Загружаем YAML если существует
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            yaml_config = yaml.safe_load(f) or {}

        # Мержим с defaults
        config = _deep_merge(config, yaml_config)
    else:
        print(f"[settings] Файл настроек не найден: {filepath}")
        print("[settings] Используются значения по умолчанию")

    return DotDict(config)


def validate_settings(settings: DotDict) -> List[str]:
    """
    Валидация настроек.

    Returns:
        Список ошибок (пустой если всё OK)
    """
    errors = []

    # LLM
    if not settings.llm.model:
        errors.append("llm.model не указан")
    if not settings.llm.base_url:
        errors.append("llm.base_url не указан")
    if settings.llm.timeout <= 0:
        errors.append("llm.timeout должен быть > 0")

    # Retriever thresholds
    for name in ["exact", "lemma", "semantic"]:
        value = settings.retriever.thresholds.get(name, 0)
        if not (0 <= value <= 1):
            errors.append(f"retriever.thresholds.{name} должен быть от 0 до 1")

    # Generator
    if settings.generator.max_retries < 1:
        errors.append("generator.max_retries должен быть >= 1")
    if settings.generator.history_length < 1:
        errors.append("generator.history_length должен быть >= 1")

    # Classifier thresholds
    high_conf = settings.classifier.thresholds.high_confidence
    min_conf = settings.classifier.thresholds.min_confidence
    if high_conf <= min_conf:
        errors.append("classifier.thresholds.high_confidence должен быть > min_confidence")

    return errors


# Глобальный экземпляр настроек (ленивая загрузка)
_settings = None


def get_settings() -> DotDict:
    """Получить глобальные настройки (singleton)"""
    global _settings
    if _settings is None:
        _settings = load_settings()
        errors = validate_settings(_settings)
        if errors:
            print("[settings] Ошибки в настройках:")
            for err in errors:
                print(f"  - {err}")
    return _settings


def reload_settings() -> DotDict:
    """Перезагрузить настройки из файла"""
    global _settings
    _settings = None
    return get_settings()


# Для удобного импорта: from settings import settings
settings = get_settings()


# =============================================================================
# CLI для проверки настроек
# =============================================================================

if __name__ == "__main__":
    import json

    print("=" * 60)
    print("ТЕКУЩИЕ НАСТРОЙКИ")
    print("=" * 60)

    s = load_settings()

    # Валидация
    errors = validate_settings(s)
    if errors:
        print("\n[!] ОШИБКИ:")
        for err in errors:
            print(f"  - {err}")
    else:
        print("\n[+] Все настройки валидны")

    # Вывод настроек
    print("\n" + "-" * 60)
    print(json.dumps(dict(s), indent=2, ensure_ascii=False))
