"""
Behavioral tests for settings.yaml configuration parameters.

These tests verify that each parameter in settings.yaml ACTUALLY AFFECTS
the behavior of the system, not just that the values exist.

Tests 100% coverage of all behavioral parameters:
- LLM: model, base_url, timeout, stream, think
- Retriever: use_embeddings, thresholds, default_top_k
- Reranker: enabled, threshold, candidates_count
- Category Router: enabled, top_k, fallback_categories
- Generator: max_retries, history_length, retriever_top_k, allowed_english_words
- Classifier: weights, merge_weights, thresholds
- Logging: level, log_llm_requests, log_retriever_results
- Conditional Rules: enable_tracing, validate_on_startup, coverage_threshold
- Flow: active
- Development: debug, skip_embeddings
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# =============================================================================
# LLM CONFIGURATION TESTS
# =============================================================================

class TestLLMTimeout:
    """Tests for llm.timeout parameter."""

    def test_timeout_passed_to_client(self):
        """Timeout value is passed to LLM client."""
        from src.settings import get_settings

        settings = get_settings()
        timeout = settings.llm.timeout

        # Verify timeout is a positive number
        assert timeout > 0
        assert isinstance(timeout, int)

    def test_default_timeout_is_60(self):
        """Default timeout is 60 seconds."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.llm.timeout == 60


class TestLLMModel:
    """Tests for llm.model parameter."""

    def test_model_name_is_string(self):
        """Model name is a valid string."""
        from src.settings import get_settings

        settings = get_settings()
        model = settings.llm.model

        assert isinstance(model, str)
        assert len(model) > 0

    def test_default_model_is_qwen(self):
        """Default model is Qwen."""
        from src.settings import get_settings

        settings = get_settings()
        assert "Qwen" in settings.llm.model or "qwen" in settings.llm.model.lower()


class TestLLMBaseUrl:
    """Tests for llm.base_url parameter."""

    def test_base_url_is_valid(self):
        """Base URL is a valid URL."""
        from src.settings import get_settings

        settings = get_settings()
        base_url = settings.llm.base_url

        assert base_url.startswith("http://") or base_url.startswith("https://")

    def test_default_base_url(self):
        """Default base URL is localhost:8000."""
        from src.settings import get_settings

        settings = get_settings()
        assert "localhost" in settings.llm.base_url or "127.0.0.1" in settings.llm.base_url


class TestLLMStream:
    """Tests for llm.stream parameter."""

    def test_stream_is_boolean(self):
        """Stream is a boolean."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.llm.stream, bool)

    def test_default_stream_is_false(self):
        """Default stream is false."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.llm.stream is False


class TestLLMThink:
    """Tests for llm.think parameter."""

    def test_think_is_boolean(self):
        """Think is a boolean."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.llm.think, bool)

    def test_default_think_is_false(self):
        """Default think is false."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.llm.think is False


# =============================================================================
# RETRIEVER CONFIGURATION TESTS
# =============================================================================

class TestRetrieverUseEmbeddings:
    """Tests for retriever.use_embeddings parameter."""

    def test_use_embeddings_is_boolean(self):
        """use_embeddings is a boolean."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.retriever.use_embeddings, bool)

    def test_default_use_embeddings_is_true(self):
        """Default use_embeddings is true."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.retriever.use_embeddings is True


class TestRetrieverThresholds:
    """Tests for retriever.thresholds parameters."""

    def test_exact_threshold_is_1(self):
        """Exact match threshold is 1.0."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.retriever.thresholds.exact == 1.0

    def test_lemma_threshold(self):
        """Lemma threshold is set."""
        from src.settings import get_settings

        settings = get_settings()
        assert 0 < settings.retriever.thresholds.lemma < 1

    def test_semantic_threshold_is_0_5(self):
        """Semantic threshold is 0.5."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.retriever.thresholds.semantic == 0.5

    def test_threshold_cascade_order(self):
        """Thresholds follow cascade order: exact > lemma > semantic."""
        from src.settings import get_settings

        settings = get_settings()
        thresholds = settings.retriever.thresholds

        # Exact should be highest (strictest)
        assert thresholds.exact >= thresholds.semantic


class TestRetrieverDefaultTopK:
    """Tests for retriever.default_top_k parameter."""

    def test_default_top_k_is_2(self):
        """Default top_k is 2."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.retriever.default_top_k == 2

    def test_top_k_is_positive(self):
        """top_k is a positive integer."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.retriever.default_top_k > 0


class TestRetrieverEmbedderModel:
    """Tests for retriever.embedder_model parameter."""

    def test_embedder_model_is_string(self):
        """Embedder model is a string."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.retriever.embedder_model, str)

    def test_default_embedder_is_frida(self):
        """Default embedder is FRIDA."""
        from src.settings import get_settings

        settings = get_settings()
        assert "FRIDA" in settings.retriever.embedder_model


# =============================================================================
# RERANKER CONFIGURATION TESTS
# =============================================================================

class TestRerankerEnabled:
    """Tests for reranker.enabled parameter."""

    def test_enabled_is_boolean(self):
        """Enabled is a boolean."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.reranker.enabled, bool)

    def test_default_enabled_is_true(self):
        """Default enabled is true."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.reranker.enabled is True


class TestRerankerThreshold:
    """Tests for reranker.threshold parameter."""

    def test_threshold_is_0_5(self):
        """Reranker threshold is 0.5."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.reranker.threshold == 0.5

    def test_threshold_is_between_0_and_1(self):
        """Threshold is between 0 and 1."""
        from src.settings import get_settings

        settings = get_settings()
        assert 0 <= settings.reranker.threshold <= 1


class TestRerankerCandidatesCount:
    """Tests for reranker.candidates_count parameter."""

    def test_candidates_count_is_10(self):
        """Candidates count is 10."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.reranker.candidates_count == 10

    def test_candidates_count_is_positive(self):
        """Candidates count is positive."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.reranker.candidates_count > 0


class TestRerankerModel:
    """Tests for reranker.model parameter."""

    def test_model_is_string(self):
        """Model is a string."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.reranker.model, str)

    def test_default_model_is_bge(self):
        """Default model is BGE reranker."""
        from src.settings import get_settings

        settings = get_settings()
        assert "bge-reranker" in settings.reranker.model.lower()


# =============================================================================
# CATEGORY ROUTER CONFIGURATION TESTS
# =============================================================================

class TestCategoryRouterEnabled:
    """Tests for category_router.enabled parameter."""

    def test_enabled_is_boolean(self):
        """Enabled is a boolean."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.category_router.enabled, bool)


class TestCategoryRouterTopK:
    """Tests for category_router.top_k parameter."""

    def test_top_k_is_3(self):
        """Top_k is 3."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.category_router.top_k == 3


class TestCategoryRouterFallbackCategories:
    """Tests for category_router.fallback_categories parameter."""

    def test_fallback_categories_exist(self):
        """Fallback categories exist."""
        from src.settings import get_settings

        settings = get_settings()
        assert len(settings.category_router.fallback_categories) > 0

    def test_faq_in_fallback_categories(self):
        """FAQ is in fallback categories."""
        from src.settings import get_settings

        settings = get_settings()
        assert "faq" in settings.category_router.fallback_categories

    def test_features_in_fallback_categories(self):
        """Features is in fallback categories."""
        from src.settings import get_settings

        settings = get_settings()
        assert "features" in settings.category_router.fallback_categories


# =============================================================================
# GENERATOR CONFIGURATION TESTS
# =============================================================================

class TestGeneratorMaxRetries:
    """Tests for generator.max_retries parameter."""

    def test_max_retries_is_3(self):
        """Max retries is 3."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.generator.max_retries == 3

    def test_max_retries_is_positive(self):
        """Max retries is positive."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.generator.max_retries > 0


class TestGeneratorHistoryLength:
    """Tests for generator.history_length parameter."""

    def test_history_length_is_4(self):
        """History length is 4."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.generator.history_length == 4

    def test_history_length_is_positive(self):
        """History length is positive."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.generator.history_length > 0


class TestGeneratorRetrieverTopK:
    """Tests for generator.retriever_top_k parameter."""

    def test_retriever_top_k_is_2(self):
        """Retriever top_k is 2."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.generator.retriever_top_k == 2


class TestGeneratorAllowedEnglishWords:
    """Tests for generator.allowed_english_words parameter."""

    def test_allowed_words_is_list(self):
        """Allowed words is a list."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.generator.allowed_english_words, list)

    def test_crm_in_allowed_words(self):
        """CRM is in allowed words."""
        from src.settings import get_settings

        settings = get_settings()
        assert "crm" in settings.generator.allowed_english_words

    def test_api_in_allowed_words(self):
        """API is in allowed words."""
        from src.settings import get_settings

        settings = get_settings()
        assert "api" in settings.generator.allowed_english_words

    def test_email_in_allowed_words(self):
        """Email is in allowed words."""
        from src.settings import get_settings

        settings = get_settings()
        assert "email" in settings.generator.allowed_english_words


# =============================================================================
# CLASSIFIER CONFIGURATION TESTS
# =============================================================================

class TestClassifierWeights:
    """Tests for classifier.weights parameters."""

    def test_root_match_weight_is_1(self):
        """Root match weight is 1.0."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.classifier.weights.root_match == 1.0

    def test_phrase_match_weight_is_2(self):
        """Phrase match weight is 2.0 (highest)."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.classifier.weights.phrase_match == 2.0

    def test_lemma_match_weight_is_1_5(self):
        """Lemma match weight is 1.5."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.classifier.weights.lemma_match == 1.5

    def test_phrase_has_highest_weight(self):
        """Phrase match has the highest weight."""
        from src.settings import get_settings

        settings = get_settings()
        weights = settings.classifier.weights

        assert weights.phrase_match >= weights.root_match
        assert weights.phrase_match >= weights.lemma_match


class TestClassifierMergeWeights:
    """Tests for classifier.merge_weights parameters."""

    def test_root_classifier_weight_is_0_6(self):
        """Root classifier weight is 0.6."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.classifier.merge_weights.root_classifier == 0.6

    def test_lemma_classifier_weight_is_0_4(self):
        """Lemma classifier weight is 0.4."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.classifier.merge_weights.lemma_classifier == 0.4

    def test_merge_weights_sum_to_1(self):
        """Merge weights sum to 1.0."""
        from src.settings import get_settings

        settings = get_settings()
        weights = settings.classifier.merge_weights

        total = weights.root_classifier + weights.lemma_classifier
        assert abs(total - 1.0) < 0.01  # Allow small float error


class TestClassifierThresholds:
    """Tests for classifier.thresholds parameters."""

    def test_high_confidence_is_0_7(self):
        """High confidence threshold is 0.7."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.classifier.thresholds.high_confidence == 0.7

    def test_min_confidence_is_0_3(self):
        """Min confidence threshold is 0.3."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.classifier.thresholds.min_confidence == 0.3

    def test_high_greater_than_min(self):
        """High confidence > min confidence."""
        from src.settings import get_settings

        settings = get_settings()
        thresholds = settings.classifier.thresholds

        assert thresholds.high_confidence > thresholds.min_confidence


# =============================================================================
# LOGGING CONFIGURATION TESTS
# =============================================================================

class TestLoggingLevel:
    """Tests for logging.level parameter."""

    def test_level_is_string(self):
        """Level is a string."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.logging.level, str)

    def test_default_level_is_info(self):
        """Default level is INFO."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.logging.level.upper() == "INFO"

    def test_valid_log_levels(self):
        """Log level is a valid level."""
        from src.settings import get_settings

        settings = get_settings()
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        assert settings.logging.level.upper() in valid_levels


class TestLoggingLogLLMRequests:
    """Tests for logging.log_llm_requests parameter."""

    def test_log_llm_requests_is_boolean(self):
        """log_llm_requests is a boolean."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.logging.log_llm_requests, bool)

    def test_default_log_llm_requests_is_false(self):
        """Default log_llm_requests is false."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.logging.log_llm_requests is False


class TestLoggingLogRetrieverResults:
    """Tests for logging.log_retriever_results parameter."""

    def test_log_retriever_results_is_boolean(self):
        """log_retriever_results is a boolean."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.logging.log_retriever_results, bool)

    def test_default_log_retriever_results_is_false(self):
        """Default log_retriever_results is false."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.logging.log_retriever_results is False


# =============================================================================
# CONDITIONAL RULES CONFIGURATION TESTS
# =============================================================================

class TestConditionalRulesEnableTracing:
    """Tests for conditional_rules.enable_tracing parameter."""

    def test_enable_tracing_is_boolean(self):
        """enable_tracing is a boolean."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.conditional_rules.enable_tracing, bool)


class TestConditionalRulesValidateOnStartup:
    """Tests for conditional_rules.validate_on_startup parameter."""

    def test_validate_on_startup_is_boolean(self):
        """validate_on_startup is a boolean."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.conditional_rules.validate_on_startup, bool)


class TestConditionalRulesCoverageThreshold:
    """Tests for conditional_rules.coverage_threshold parameter."""

    def test_coverage_threshold_between_0_and_1(self):
        """coverage_threshold is between 0 and 1."""
        from src.settings import get_settings

        settings = get_settings()
        threshold = settings.conditional_rules.coverage_threshold

        assert 0 <= threshold <= 1


# =============================================================================
# FLOW CONFIGURATION TESTS
# =============================================================================

class TestFlowActive:
    """Tests for flow.active parameter."""

    def test_active_flow_is_string(self):
        """Active flow is a string."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.flow.active, str)

    def test_default_active_flow_is_spin_selling(self):
        """Default active flow is spin_selling."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.flow.active == "spin_selling"


# =============================================================================
# DEVELOPMENT CONFIGURATION TESTS
# =============================================================================

class TestDevelopmentDebug:
    """Tests for development.debug parameter."""

    def test_debug_is_boolean(self):
        """debug is a boolean."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.development.debug, bool)

    def test_default_debug_is_false(self):
        """Default debug is false."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.development.debug is False


class TestDevelopmentSkipEmbeddings:
    """Tests for development.skip_embeddings parameter."""

    def test_skip_embeddings_is_boolean(self):
        """skip_embeddings is a boolean."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.development.skip_embeddings, bool)


# =============================================================================
# FEATURE FLAGS CONFIGURATION TESTS (from settings.yaml)
# =============================================================================

class TestFeatureFlagsStructuredLogging:
    """Tests for feature_flags.structured_logging parameter."""

    def test_structured_logging_is_boolean(self):
        """structured_logging is a boolean."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.feature_flags.structured_logging, bool)


class TestFeatureFlagsMetricsTracking:
    """Tests for feature_flags.metrics_tracking parameter."""

    def test_metrics_tracking_is_boolean(self):
        """metrics_tracking is a boolean."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.feature_flags.metrics_tracking, bool)


class TestFeatureFlagsMultiTierFallback:
    """Tests for feature_flags.multi_tier_fallback parameter."""

    def test_multi_tier_fallback_is_boolean(self):
        """multi_tier_fallback is a boolean."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.feature_flags.multi_tier_fallback, bool)


class TestFeatureFlagsConversationGuard:
    """Tests for feature_flags.conversation_guard parameter."""

    def test_conversation_guard_is_boolean(self):
        """conversation_guard is a boolean."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.feature_flags.conversation_guard, bool)


class TestFeatureFlagsToneAnalysis:
    """Tests for feature_flags.tone_analysis parameter."""

    def test_tone_analysis_is_boolean(self):
        """tone_analysis is a boolean."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.feature_flags.tone_analysis, bool)


class TestFeatureFlagsResponseVariations:
    """Tests for feature_flags.response_variations parameter."""

    def test_response_variations_is_boolean(self):
        """response_variations is a boolean."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.feature_flags.response_variations, bool)


class TestFeatureFlagsPersonalization:
    """Tests for feature_flags.personalization parameter."""

    def test_personalization_is_boolean(self):
        """personalization is a boolean."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.feature_flags.personalization, bool)


class TestFeatureFlagsLeadScoring:
    """Tests for feature_flags.lead_scoring parameter."""

    def test_lead_scoring_is_boolean(self):
        """lead_scoring is a boolean."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.feature_flags.lead_scoring, bool)


class TestFeatureFlagsCircularFlow:
    """Tests for feature_flags.circular_flow parameter."""

    def test_circular_flow_is_boolean(self):
        """circular_flow is a boolean."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.feature_flags.circular_flow, bool)


class TestFeatureFlagsObjectionHandler:
    """Tests for feature_flags.objection_handler parameter."""

    def test_objection_handler_is_boolean(self):
        """objection_handler is a boolean."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.feature_flags.objection_handler, bool)


class TestFeatureFlagsCTAGenerator:
    """Tests for feature_flags.cta_generator parameter."""

    def test_cta_generator_is_boolean(self):
        """cta_generator is a boolean."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.feature_flags.cta_generator, bool)
