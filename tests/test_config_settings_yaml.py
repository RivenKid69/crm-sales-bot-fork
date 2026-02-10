"""
Comprehensive tests for settings.yaml configuration parameters.

Tests 100% coverage of all parameters in settings.yaml:
- LLM configuration
- Retriever configuration
- Reranker configuration
- Category router configuration
- Generator configuration
- Classifier configuration
- Logging configuration
- Conditional rules configuration
- Flow configuration
- Feature flags
- Development settings
"""

import pytest
import tempfile
from pathlib import Path
import yaml

import sys

from src.settings import (
    load_settings, validate_settings, DotDict, DEFAULTS,
    _deep_merge, get_settings, reload_settings, SETTINGS_FILE
)

class TestLLMConfiguration:
    """Tests for LLM configuration section."""

    def test_llm_model_parameter(self):
        """Test llm.model parameter is loaded correctly."""
        yaml_content = """
llm:
  model: "TestModel/Test-4B"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.llm.model == "TestModel/Test-4B"

    def test_llm_model_default(self):
        """Test llm.model uses default when not specified."""
        settings = load_settings(Path("/nonexistent.yaml"))
        assert settings.llm.model == DEFAULTS["llm"]["model"]

    def test_llm_base_url_parameter(self):
        """Test llm.base_url parameter."""
        yaml_content = """
llm:
  base_url: "http://custom-server:9000/v1"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.llm.base_url == "http://custom-server:9000/v1"

    def test_llm_timeout_parameter(self):
        """Test llm.timeout parameter."""
        yaml_content = """
llm:
  timeout: 120
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.llm.timeout == 120

    def test_llm_timeout_validation_positive(self):
        """Test llm.timeout must be positive."""
        settings_dict = _deep_merge({}, DEFAULTS)
        settings_dict["llm"]["timeout"] = 0
        settings = DotDict(settings_dict)
        errors = validate_settings(settings)
        assert any("timeout" in e.lower() for e in errors)

    def test_llm_timeout_validation_negative(self):
        """Test llm.timeout rejects negative values."""
        settings_dict = _deep_merge({}, DEFAULTS)
        settings_dict["llm"]["timeout"] = -10
        settings = DotDict(settings_dict)
        errors = validate_settings(settings)
        assert any("timeout" in e.lower() for e in errors)

    def test_llm_stream_parameter_false(self):
        """Test llm.stream parameter when false."""
        yaml_content = """
llm:
  stream: false
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.llm.stream is False

    def test_llm_stream_parameter_true(self):
        """Test llm.stream parameter when true."""
        yaml_content = """
llm:
  stream: true
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.llm.stream is True

    def test_llm_think_parameter_false(self):
        """Test llm.think parameter when false."""
        yaml_content = """
llm:
  think: false
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.llm.think is False

    def test_llm_think_parameter_true(self):
        """Test llm.think parameter when true."""
        yaml_content = """
llm:
  think: true
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.llm.think is True

class TestRetrieverConfiguration:
    """Tests for retriever configuration section."""

    def test_use_embeddings_true(self):
        """Test retriever.use_embeddings when true."""
        yaml_content = """
retriever:
  use_embeddings: true
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.retriever.use_embeddings is True

    def test_use_embeddings_false(self):
        """Test retriever.use_embeddings when false."""
        yaml_content = """
retriever:
  use_embeddings: false
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.retriever.use_embeddings is False

    def test_embedder_model_parameter(self):
        """Test retriever.embedder_model parameter."""
        yaml_content = """
retriever:
  embedder_model: "custom-embedder/model"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.retriever.embedder_model == "custom-embedder/model"

    def test_threshold_exact(self):
        """Test retriever.thresholds.exact parameter."""
        yaml_content = """
retriever:
  thresholds:
    exact: 0.95
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.retriever.thresholds.exact == 0.95

    def test_threshold_exact_validation_above_one(self):
        """Test retriever.thresholds.exact rejects values > 1."""
        settings_dict = _deep_merge({}, DEFAULTS)
        settings_dict["retriever"]["thresholds"]["exact"] = 1.5
        settings = DotDict(settings_dict)
        errors = validate_settings(settings)
        assert any("exact" in e.lower() for e in errors)

    def test_threshold_exact_validation_negative(self):
        """Test retriever.thresholds.exact rejects negative values."""
        settings_dict = _deep_merge({}, DEFAULTS)
        settings_dict["retriever"]["thresholds"]["exact"] = -0.1
        settings = DotDict(settings_dict)
        errors = validate_settings(settings)
        assert any("exact" in e.lower() for e in errors)

    def test_threshold_lemma(self):
        """Test retriever.thresholds.lemma parameter."""
        yaml_content = """
retriever:
  thresholds:
    lemma: 0.25
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.retriever.thresholds.lemma == 0.25

    def test_threshold_lemma_validation(self):
        """Test retriever.thresholds.lemma validation."""
        settings_dict = _deep_merge({}, DEFAULTS)
        settings_dict["retriever"]["thresholds"]["lemma"] = 2.0
        settings = DotDict(settings_dict)
        errors = validate_settings(settings)
        assert any("lemma" in e.lower() for e in errors)

    def test_threshold_semantic(self):
        """Test retriever.thresholds.semantic parameter."""
        yaml_content = """
retriever:
  thresholds:
    semantic: 0.6
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.retriever.thresholds.semantic == 0.6

    def test_threshold_semantic_validation(self):
        """Test retriever.thresholds.semantic validation."""
        settings_dict = _deep_merge({}, DEFAULTS)
        settings_dict["retriever"]["thresholds"]["semantic"] = -0.5
        settings = DotDict(settings_dict)
        errors = validate_settings(settings)
        assert any("semantic" in e.lower() for e in errors)

    def test_default_top_k(self):
        """Test retriever.default_top_k parameter."""
        yaml_content = """
retriever:
  default_top_k: 5
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.retriever.default_top_k == 5

class TestRerankerConfiguration:
    """Tests for reranker configuration section."""

    def test_reranker_enabled_true(self):
        """Test reranker.enabled when true."""
        yaml_content = """
reranker:
  enabled: true
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.reranker.enabled is True

    def test_reranker_enabled_false(self):
        """Test reranker.enabled when false."""
        yaml_content = """
reranker:
  enabled: false
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.reranker.enabled is False

    def test_reranker_model(self):
        """Test reranker.model parameter."""
        yaml_content = """
reranker:
  model: "custom-reranker/model"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.reranker.model == "custom-reranker/model"

    def test_reranker_threshold(self):
        """Test reranker.threshold parameter."""
        yaml_content = """
reranker:
  threshold: 0.7
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.reranker.threshold == 0.7

    def test_reranker_candidates_count(self):
        """Test reranker.candidates_count parameter."""
        yaml_content = """
reranker:
  candidates_count: 15
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.reranker.candidates_count == 15

class TestCategoryRouterConfiguration:
    """Tests for category_router configuration section."""

    def test_category_router_enabled_true(self):
        """Test category_router.enabled when true."""
        yaml_content = """
category_router:
  enabled: true
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.category_router.enabled is True

    def test_category_router_enabled_false(self):
        """Test category_router.enabled when false."""
        yaml_content = """
category_router:
  enabled: false
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.category_router.enabled is False

    def test_category_router_top_k(self):
        """Test category_router.top_k parameter."""
        yaml_content = """
category_router:
  top_k: 5
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.category_router.top_k == 5

    def test_category_router_fallback_categories(self):
        """Test category_router.fallback_categories parameter."""
        yaml_content = """
category_router:
  fallback_categories:
    - "pricing"
    - "support"
    - "features"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.category_router.fallback_categories == ["pricing", "support", "features"]

class TestGeneratorConfiguration:
    """Tests for generator configuration section."""

    def test_generator_max_retries(self):
        """Test generator.max_retries parameter."""
        yaml_content = """
generator:
  max_retries: 5
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.generator.max_retries == 5

    def test_generator_max_retries_validation(self):
        """Test generator.max_retries must be >= 1."""
        settings_dict = _deep_merge({}, DEFAULTS)
        settings_dict["generator"]["max_retries"] = 0
        settings = DotDict(settings_dict)
        errors = validate_settings(settings)
        assert any("max_retries" in e.lower() for e in errors)

    def test_generator_history_length(self):
        """Test generator.history_length parameter."""
        yaml_content = """
generator:
  history_length: 8
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.generator.history_length == 8

    def test_generator_history_length_validation(self):
        """Test generator.history_length must be >= 1."""
        settings_dict = _deep_merge({}, DEFAULTS)
        settings_dict["generator"]["history_length"] = 0
        settings = DotDict(settings_dict)
        errors = validate_settings(settings)
        assert any("history_length" in e.lower() for e in errors)

    def test_generator_retriever_top_k(self):
        """Test generator.retriever_top_k parameter."""
        yaml_content = """
generator:
  retriever_top_k: 3
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.generator.retriever_top_k == 3

    def test_generator_allowed_english_words(self):
        """Test generator.allowed_english_words parameter."""
        yaml_content = """
generator:
  allowed_english_words:
    - "crm"
    - "api"
    - "sms"
    - "custom_word"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert "crm" in settings.generator.allowed_english_words
            assert "custom_word" in settings.generator.allowed_english_words

class TestClassifierConfiguration:
    """Tests for classifier configuration section."""

    def test_classifier_weights_root_match(self):
        """Test classifier.weights.root_match parameter."""
        yaml_content = """
classifier:
  weights:
    root_match: 1.5
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.classifier.weights.root_match == 1.5

    def test_classifier_weights_phrase_match(self):
        """Test classifier.weights.phrase_match parameter."""
        yaml_content = """
classifier:
  weights:
    phrase_match: 3.0
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.classifier.weights.phrase_match == 3.0

    def test_classifier_weights_lemma_match(self):
        """Test classifier.weights.lemma_match parameter."""
        yaml_content = """
classifier:
  weights:
    lemma_match: 2.0
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.classifier.weights.lemma_match == 2.0

    def test_classifier_merge_weights_root_classifier(self):
        """Test classifier.merge_weights.root_classifier parameter."""
        yaml_content = """
classifier:
  merge_weights:
    root_classifier: 0.7
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.classifier.merge_weights.root_classifier == 0.7

    def test_classifier_merge_weights_lemma_classifier(self):
        """Test classifier.merge_weights.lemma_classifier parameter."""
        yaml_content = """
classifier:
  merge_weights:
    lemma_classifier: 0.3
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.classifier.merge_weights.lemma_classifier == 0.3

    def test_classifier_thresholds_high_confidence(self):
        """Test classifier.thresholds.high_confidence parameter."""
        yaml_content = """
classifier:
  thresholds:
    high_confidence: 0.8
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.classifier.thresholds.high_confidence == 0.8

    def test_classifier_thresholds_min_confidence(self):
        """Test classifier.thresholds.min_confidence parameter."""
        yaml_content = """
classifier:
  thresholds:
    min_confidence: 0.4
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.classifier.thresholds.min_confidence == 0.4

    def test_classifier_thresholds_validation_order(self):
        """Test high_confidence must be > min_confidence."""
        settings_dict = _deep_merge({}, DEFAULTS)
        settings_dict["classifier"]["thresholds"]["high_confidence"] = 0.3
        settings_dict["classifier"]["thresholds"]["min_confidence"] = 0.5
        settings = DotDict(settings_dict)
        errors = validate_settings(settings)
        assert any("high_confidence" in e.lower() for e in errors)

class TestLoggingConfiguration:
    """Tests for logging configuration section."""

    def test_logging_level_info(self):
        """Test logging.level = INFO."""
        yaml_content = """
logging:
  level: "INFO"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.logging.level == "INFO"

    def test_logging_level_debug(self):
        """Test logging.level = DEBUG."""
        yaml_content = """
logging:
  level: "DEBUG"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.logging.level == "DEBUG"

    def test_logging_level_warning(self):
        """Test logging.level = WARNING."""
        yaml_content = """
logging:
  level: "WARNING"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.logging.level == "WARNING"

    def test_logging_level_error(self):
        """Test logging.level = ERROR."""
        yaml_content = """
logging:
  level: "ERROR"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.logging.level == "ERROR"

    def test_logging_log_llm_requests_true(self):
        """Test logging.log_llm_requests when true."""
        yaml_content = """
logging:
  log_llm_requests: true
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.logging.log_llm_requests is True

    def test_logging_log_llm_requests_false(self):
        """Test logging.log_llm_requests when false."""
        yaml_content = """
logging:
  log_llm_requests: false
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.logging.log_llm_requests is False

    def test_logging_log_retriever_results_true(self):
        """Test logging.log_retriever_results when true."""
        yaml_content = """
logging:
  log_retriever_results: true
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.logging.log_retriever_results is True

    def test_logging_log_retriever_results_false(self):
        """Test logging.log_retriever_results when false."""
        yaml_content = """
logging:
  log_retriever_results: false
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.logging.log_retriever_results is False

class TestConditionalRulesConfiguration:
    """Tests for conditional_rules configuration section."""

    def test_enable_tracing_true(self):
        """Test conditional_rules.enable_tracing when true."""
        yaml_content = """
conditional_rules:
  enable_tracing: true
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.conditional_rules.enable_tracing is True

    def test_enable_tracing_false(self):
        """Test conditional_rules.enable_tracing when false."""
        yaml_content = """
conditional_rules:
  enable_tracing: false
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.conditional_rules.enable_tracing is False

    def test_log_level_info(self):
        """Test conditional_rules.log_level = INFO."""
        yaml_content = """
conditional_rules:
  log_level: "INFO"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.conditional_rules.log_level == "INFO"

    def test_log_level_debug(self):
        """Test conditional_rules.log_level = DEBUG."""
        yaml_content = """
conditional_rules:
  log_level: "DEBUG"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.conditional_rules.log_level == "DEBUG"

    def test_log_context_true(self):
        """Test conditional_rules.log_context when true."""
        yaml_content = """
conditional_rules:
  log_context: true
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.conditional_rules.log_context is True

    def test_log_context_false(self):
        """Test conditional_rules.log_context when false."""
        yaml_content = """
conditional_rules:
  log_context: false
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.conditional_rules.log_context is False

    def test_log_each_condition_true(self):
        """Test conditional_rules.log_each_condition when true."""
        yaml_content = """
conditional_rules:
  log_each_condition: true
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.conditional_rules.log_each_condition is True

    def test_log_each_condition_false(self):
        """Test conditional_rules.log_each_condition when false."""
        yaml_content = """
conditional_rules:
  log_each_condition: false
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.conditional_rules.log_each_condition is False

    def test_validate_on_startup_true(self):
        """Test conditional_rules.validate_on_startup when true."""
        yaml_content = """
conditional_rules:
  validate_on_startup: true
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.conditional_rules.validate_on_startup is True

    def test_validate_on_startup_false(self):
        """Test conditional_rules.validate_on_startup when false."""
        yaml_content = """
conditional_rules:
  validate_on_startup: false
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.conditional_rules.validate_on_startup is False

    def test_coverage_threshold(self):
        """Test conditional_rules.coverage_threshold parameter."""
        yaml_content = """
conditional_rules:
  coverage_threshold: 0.9
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.conditional_rules.coverage_threshold == 0.9

class TestFlowConfiguration:
    """Tests for flow configuration section."""

    def test_flow_active_spin_selling(self):
        """Test flow.active = spin_selling."""
        yaml_content = """
flow:
  active: "spin_selling"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.flow.active == "spin_selling"

    def test_flow_active_custom(self):
        """Test flow.active with custom flow name."""
        yaml_content = """
flow:
  active: "custom_flow"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.flow.active == "custom_flow"

class TestFeatureFlagsConfiguration:
    """Tests for feature_flags configuration section."""

    def test_structured_logging_true(self):
        """Test feature_flags.structured_logging when true."""
        yaml_content = """
feature_flags:
  structured_logging: true
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.feature_flags.structured_logging is True

    def test_structured_logging_false(self):
        """Test feature_flags.structured_logging when false."""
        yaml_content = """
feature_flags:
  structured_logging: false
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.feature_flags.structured_logging is False

    def test_metrics_tracking_true(self):
        """Test feature_flags.metrics_tracking when true."""
        yaml_content = """
feature_flags:
  metrics_tracking: true
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.feature_flags.metrics_tracking is True

    def test_multi_tier_fallback_true(self):
        """Test feature_flags.multi_tier_fallback when true."""
        yaml_content = """
feature_flags:
  multi_tier_fallback: true
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.feature_flags.multi_tier_fallback is True

    def test_conversation_guard_true(self):
        """Test feature_flags.conversation_guard when true."""
        yaml_content = """
feature_flags:
  conversation_guard: true
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.feature_flags.conversation_guard is True

    def test_tone_analysis_true(self):
        """Test feature_flags.tone_analysis when true."""
        yaml_content = """
feature_flags:
  tone_analysis: true
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.feature_flags.tone_analysis is True

    def test_tone_analysis_false(self):
        """Test feature_flags.tone_analysis when false."""
        yaml_content = """
feature_flags:
  tone_analysis: false
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.feature_flags.tone_analysis is False

    def test_response_variations_true(self):
        """Test feature_flags.response_variations when true."""
        yaml_content = """
feature_flags:
  response_variations: true
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.feature_flags.response_variations is True

    def test_personalization_true(self):
        """Test feature_flags.personalization when true."""
        yaml_content = """
feature_flags:
  personalization: true
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.feature_flags.personalization is True

    def test_personalization_false(self):
        """Test feature_flags.personalization when false."""
        yaml_content = """
feature_flags:
  personalization: false
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.feature_flags.personalization is False

    def test_lead_scoring_true(self):
        """Test feature_flags.lead_scoring when true."""
        yaml_content = """
feature_flags:
  lead_scoring: true
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.feature_flags.lead_scoring is True

    def test_lead_scoring_false(self):
        """Test feature_flags.lead_scoring when false."""
        yaml_content = """
feature_flags:
  lead_scoring: false
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.feature_flags.lead_scoring is False

    def test_circular_flow_true(self):
        """Test feature_flags.circular_flow when true."""
        yaml_content = """
feature_flags:
  circular_flow: true
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.feature_flags.circular_flow is True

    def test_circular_flow_false(self):
        """Test feature_flags.circular_flow when false."""
        yaml_content = """
feature_flags:
  circular_flow: false
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.feature_flags.circular_flow is False

    def test_objection_handler_true(self):
        """Test feature_flags.objection_handler when true."""
        yaml_content = """
feature_flags:
  objection_handler: true
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.feature_flags.objection_handler is True

    def test_objection_handler_false(self):
        """Test feature_flags.objection_handler when false."""
        yaml_content = """
feature_flags:
  objection_handler: false
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.feature_flags.objection_handler is False

    def test_cta_generator_true(self):
        """Test feature_flags.cta_generator when true."""
        yaml_content = """
feature_flags:
  cta_generator: true
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.feature_flags.cta_generator is True

    def test_cta_generator_false(self):
        """Test feature_flags.cta_generator when false."""
        yaml_content = """
feature_flags:
  cta_generator: false
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.feature_flags.cta_generator is False

class TestDevelopmentConfiguration:
    """Tests for development configuration section."""

    def test_debug_true(self):
        """Test development.debug when true."""
        yaml_content = """
development:
  debug: true
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.development.debug is True

    def test_debug_false(self):
        """Test development.debug when false."""
        yaml_content = """
development:
  debug: false
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.development.debug is False

    def test_skip_embeddings_true(self):
        """Test development.skip_embeddings when true."""
        yaml_content = """
development:
  skip_embeddings: true
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.development.skip_embeddings is True

    def test_skip_embeddings_false(self):
        """Test development.skip_embeddings when false."""
        yaml_content = """
development:
  skip_embeddings: false
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = load_settings(Path(f.name))
            assert settings.development.skip_embeddings is False

class TestCompleteSettingsYaml:
    """Tests for complete settings.yaml file loading."""

    def test_load_actual_settings_file(self):
        """Test loading the actual settings.yaml file."""
        if SETTINGS_FILE.exists():
            settings = load_settings(SETTINGS_FILE)

            # Verify all top-level sections exist
            assert hasattr(settings, 'llm')
            assert hasattr(settings, 'retriever')
            assert hasattr(settings, 'generator')
            assert hasattr(settings, 'classifier')
            assert hasattr(settings, 'logging')
            assert hasattr(settings, 'conditional_rules')
            assert hasattr(settings, 'flow')

            # Verify nested access works
            assert settings.llm.model is not None
            assert settings.retriever.thresholds.lemma is not None

    def test_actual_settings_pass_validation(self):
        """Test that actual settings.yaml passes validation."""
        if SETTINGS_FILE.exists():
            settings = load_settings(SETTINGS_FILE)
            errors = validate_settings(settings)
            assert errors == [], f"Validation errors: {errors}"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
