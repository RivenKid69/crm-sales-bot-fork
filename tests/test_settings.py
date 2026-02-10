"""
Тесты для системы настроек.
"""

import pytest
import tempfile
from pathlib import Path

import sys

from src.settings import load_settings, validate_settings, DotDict, DEFAULTS

class TestDotDict:
    """Тесты для DotDict"""

    def test_dot_access(self):
        d = DotDict({"a": 1, "b": {"c": 2}})
        assert d.a == 1
        assert d.b.c == 2

    def test_nested_dict(self):
        d = DotDict({"level1": {"level2": {"level3": "value"}}})
        assert d.level1.level2.level3 == "value"

    def test_missing_key_raises(self):
        d = DotDict({"a": 1})
        with pytest.raises(AttributeError):
            _ = d.nonexistent

    def test_get_nested(self):
        d = DotDict({"a": {"b": {"c": 3}}})
        assert d.get_nested("a.b.c") == 3
        assert d.get_nested("a.b.x", "default") == "default"

    def test_set_attr(self):
        d = DotDict({})
        d.foo = "bar"
        assert d["foo"] == "bar"
        assert d.foo == "bar"

class TestLoadSettings:
    """Тесты загрузки настроек"""

    def test_load_defaults_when_no_file(self):
        """Если файла нет — используются defaults"""
        settings = load_settings(Path("/nonexistent/path.yaml"))
        assert settings.llm.model == DEFAULTS["llm"]["model"]

    def test_load_from_yaml(self):
        """Загрузка из YAML файла"""
        yaml_content = """
llm:
  model: "test-model"
  timeout: 120
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()

            settings = load_settings(Path(f.name))

            # Переопределённые значения
            assert settings.llm.model == "test-model"
            assert settings.llm.timeout == 120

            # Значения по умолчанию
            assert settings.llm.base_url == DEFAULTS["llm"]["base_url"]

    def test_deep_merge(self):
        """Глубокое слияние настроек"""
        yaml_content = """
retriever:
  thresholds:
    lemma: 0.25
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()

            settings = load_settings(Path(f.name))

            # Переопределено
            assert settings.retriever.thresholds.lemma == 0.25

            # Не затронуто
            assert settings.retriever.thresholds.exact == DEFAULTS["retriever"]["thresholds"]["exact"]
            assert settings.retriever.thresholds.semantic == DEFAULTS["retriever"]["thresholds"]["semantic"]

    def test_empty_yaml(self):
        """Пустой YAML файл — используются defaults"""
        yaml_content = ""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()

            settings = load_settings(Path(f.name))
            assert settings.llm.model == DEFAULTS["llm"]["model"]

class TestValidateSettings:
    """Тесты валидации"""

    def test_valid_defaults(self):
        """Defaults должны проходить валидацию"""
        settings = DotDict(DEFAULTS)
        errors = validate_settings(settings)
        assert errors == []

    def test_invalid_timeout(self):
        """Отрицательный timeout — ошибка"""
        from src.settings import _deep_merge
        settings_dict = _deep_merge({}, DEFAULTS)
        settings_dict["llm"]["timeout"] = -1
        settings = DotDict(settings_dict)
        errors = validate_settings(settings)
        assert any("timeout" in e for e in errors)

    def test_invalid_threshold(self):
        """Threshold вне диапазона — ошибка"""
        from src.settings import _deep_merge
        settings_dict = _deep_merge({}, DEFAULTS)
        settings_dict["retriever"]["thresholds"]["lemma"] = 1.5
        settings = DotDict(settings_dict)
        errors = validate_settings(settings)
        assert any("lemma" in e for e in errors)

    def test_invalid_confidence_order(self):
        """high_confidence <= min_confidence — ошибка"""
        from src.settings import _deep_merge
        settings_dict = _deep_merge({}, DEFAULTS)
        settings_dict["classifier"]["thresholds"]["high_confidence"] = 0.2
        settings_dict["classifier"]["thresholds"]["min_confidence"] = 0.5
        settings = DotDict(settings_dict)
        errors = validate_settings(settings)
        assert any("high_confidence" in e for e in errors)

class TestSettingsIntegration:
    """Интеграционные тесты"""

    def test_llm_uses_settings(self):
        """LLM использует настройки"""
        from src.llm import OllamaLLM
        from src.settings import settings

        llm = OllamaLLM()
        assert llm.model == settings.llm.model
        assert llm.base_url == settings.llm.base_url

    def test_retriever_uses_settings(self):
        """Retriever использует настройки"""
        from src.knowledge.retriever import CascadeRetriever
        from src.settings import settings

        retriever = CascadeRetriever(use_embeddings=False)
        assert retriever.exact_threshold == settings.retriever.thresholds.exact
        assert retriever.lemma_threshold == settings.retriever.thresholds.lemma

    def test_override_in_constructor(self):
        """Можно переопределить в конструкторе"""
        from src.llm import OllamaLLM

        llm = OllamaLLM(model="custom-model", timeout=999)
        assert llm.model == "custom-model"
        assert llm.timeout == 999

    def test_generator_uses_settings(self):
        """Generator использует настройки"""
        from src.generator import ResponseGenerator
        from src.settings import settings

        class MockLLM:
            def generate(self, prompt):
                return "Mock"

        gen = ResponseGenerator(MockLLM())
        assert gen.max_retries == settings.generator.max_retries
        assert gen.history_length == settings.generator.history_length
        assert gen.retriever_top_k == settings.generator.retriever_top_k

class TestBackwardsCompatibility:
    """Тесты обратной совместимости"""

    def test_classifier_config_exists(self):
        """CLASSIFIER_CONFIG всё ещё работает"""
        from src.config import CLASSIFIER_CONFIG

        assert "root_match_weight" in CLASSIFIER_CONFIG
        assert "high_confidence_threshold" in CLASSIFIER_CONFIG

    def test_classifier_config_uses_settings(self):
        """CLASSIFIER_CONFIG использует значения из settings"""
        from src.config import CLASSIFIER_CONFIG
        from src.settings import settings

        assert CLASSIFIER_CONFIG["root_match_weight"] == settings.classifier.weights.root_match
        assert CLASSIFIER_CONFIG["phrase_match_weight"] == settings.classifier.weights.phrase_match

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
