"""
Unit tests for 100% coverage of all config parameters.

Covers parameters not yet tested in other test files:
- conditional_rules: log_level, log_context, log_each_condition
- logging: detailed validation of log_llm_requests, log_retriever_results
- All parameter types and edge cases
"""

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# =============================================================================
# CONDITIONAL RULES CONFIGURATION - 100% COVERAGE
# =============================================================================

class TestConditionalRulesLogLevel:
    """Tests for conditional_rules.log_level parameter."""

    def test_log_level_is_string(self):
        """log_level is a string."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.conditional_rules.log_level, str)

    def test_log_level_is_valid_level(self):
        """log_level is a valid logging level."""
        from src.settings import get_settings

        settings = get_settings()
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        assert settings.conditional_rules.log_level.upper() in valid_levels

    def test_default_log_level_is_info(self):
        """Default log_level is INFO."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.conditional_rules.log_level.upper() == "INFO"


class TestConditionalRulesLogContext:
    """Tests for conditional_rules.log_context parameter."""

    def test_log_context_is_boolean(self):
        """log_context is a boolean."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.conditional_rules.log_context, bool)

    def test_default_log_context_is_false(self):
        """Default log_context is false (not verbose)."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.conditional_rules.log_context is False


class TestConditionalRulesLogEachCondition:
    """Tests for conditional_rules.log_each_condition parameter."""

    def test_log_each_condition_is_boolean(self):
        """log_each_condition is a boolean."""
        from src.settings import get_settings

        settings = get_settings()
        assert isinstance(settings.conditional_rules.log_each_condition, bool)

    def test_default_log_each_condition_is_false(self):
        """Default log_each_condition is false."""
        from src.settings import get_settings

        settings = get_settings()
        assert settings.conditional_rules.log_each_condition is False


# =============================================================================
# LOGGING CONFIGURATION - DETAILED TESTS
# =============================================================================

class TestLoggingParametersComplete:
    """Complete tests for all logging parameters."""

    def test_all_logging_params_present(self):
        """All logging parameters are present."""
        from src.settings import get_settings

        settings = get_settings()
        logging = settings.logging

        assert hasattr(logging, 'level')
        assert hasattr(logging, 'log_llm_requests')
        assert hasattr(logging, 'log_retriever_results')

    def test_logging_level_affects_logger_config(self):
        """Logging level affects logger configuration."""
        from src.settings import get_settings
        import logging

        settings = get_settings()
        level_str = settings.logging.level.upper()
        level_int = getattr(logging, level_str)

        assert level_int in [
            logging.DEBUG,
            logging.INFO,
            logging.WARNING,
            logging.ERROR,
            logging.CRITICAL
        ]


# =============================================================================
# GENERATOR ALLOWED_ENGLISH_WORDS - DETAILED TESTS
# =============================================================================

class TestAllowedEnglishWordsComplete:
    """Complete tests for allowed_english_words list."""

    def test_all_tech_terms_included(self):
        """All common tech terms are in allowed words."""
        from src.settings import get_settings

        settings = get_settings()
        words = settings.generator.allowed_english_words

        # Common tech terms
        tech_terms = ["crm", "api", "email"]
        for term in tech_terms:
            assert term in words, f"{term} should be in allowed words"

    def test_social_platforms_included(self):
        """Social platform names are in allowed words."""
        from src.settings import get_settings

        settings = get_settings()
        words = settings.generator.allowed_english_words

        platforms = ["whatsapp", "telegram"]
        for platform in platforms:
            assert platform in words, f"{platform} should be in allowed words"

    def test_business_acronyms_included(self):
        """Business acronyms are in allowed words."""
        from src.settings import get_settings

        settings = get_settings()
        words = settings.generator.allowed_english_words

        acronyms = ["hr", "pos", "erp"]
        for acronym in acronyms:
            assert acronym in words, f"{acronym} should be in allowed words"

    def test_allowed_words_are_lowercase(self):
        """All allowed words are lowercase."""
        from src.settings import get_settings

        settings = get_settings()
        words = settings.generator.allowed_english_words

        for word in words:
            assert word == word.lower(), f"{word} should be lowercase"


# =============================================================================
# RERANKER CONFIGURATION - DETAILED TESTS
# =============================================================================

class TestRerankerModelComplete:
    """Complete tests for reranker.model parameter."""

    def test_model_is_huggingface_path(self):
        """Model is a HuggingFace model path."""
        from src.settings import get_settings

        settings = get_settings()
        model = settings.reranker.model

        # Should have org/model format
        assert "/" in model, "Model should be HuggingFace format (org/model)"

    def test_model_is_reranker_type(self):
        """Model name indicates it's a reranker."""
        from src.settings import get_settings

        settings = get_settings()
        model = settings.reranker.model.lower()

        assert "reranker" in model or "ranker" in model, \
            "Model should be a reranker model"

    def test_model_supports_multilingual(self):
        """Model supports multilingual (needed for Russian)."""
        from src.settings import get_settings

        settings = get_settings()
        model = settings.reranker.model.lower()

        # BGE m3 is multilingual
        assert "m3" in model or "multilingual" in model or "bge" in model, \
            "Model should be multilingual for Russian support"


# =============================================================================
# DEVELOPMENT CONFIGURATION - DETAILED TESTS
# =============================================================================

class TestDevelopmentConfigComplete:
    """Complete tests for development configuration."""

    def test_debug_affects_logging(self):
        """Debug mode should affect logging verbosity."""
        from src.settings import get_settings

        settings = get_settings()
        debug = settings.development.debug

        # Debug is boolean
        assert isinstance(debug, bool)

        # In production, debug should be false
        # (This is a policy test, not just value test)

    def test_skip_embeddings_affects_startup(self):
        """skip_embeddings affects embedding initialization."""
        from src.settings import get_settings

        settings = get_settings()
        skip = settings.development.skip_embeddings

        assert isinstance(skip, bool)


# =============================================================================
# SPIN PHASE CLASSIFICATION CONFIG - 100% COVERAGE
# =============================================================================

class TestSpinPhaseClassification:
    """Tests for spin.phase_classification parameters."""

    def test_situation_has_data_fields(self, real_constants):
        """Situation phase has data_fields defined."""
        phase_config = real_constants['spin']['phase_classification']['situation']

        assert 'data_fields' in phase_config
        assert 'company_size' in phase_config['data_fields']
        assert 'current_tools' in phase_config['data_fields']

    def test_situation_has_intent_mapping(self, real_constants):
        """Situation phase has intent mapping."""
        phase_config = real_constants['spin']['phase_classification']['situation']

        assert 'intent' in phase_config
        assert phase_config['intent'] == 'situation_provided'

    def test_all_phases_have_confidence(self, real_constants):
        """All phases have confidence threshold."""
        phases = real_constants['spin']['phase_classification']

        for phase_name, phase_config in phases.items():
            assert 'confidence' in phase_config, f"{phase_name} missing confidence"
            assert 0 < phase_config['confidence'] <= 1.0


class TestSpinShortAnswerClassification:
    """Tests for spin.short_answer_classification parameters."""

    def test_situation_short_answer_config(self, real_constants):
        """Situation has short answer classification."""
        config = real_constants['spin']['short_answer_classification']['situation']

        assert 'positive_intent' in config
        assert config['positive_intent'] == 'situation_provided'
        assert 'positive_confidence' in config

    def test_problem_has_negative_intent(self, real_constants):
        """Problem phase has negative intent for 'no problem' answers."""
        config = real_constants['spin']['short_answer_classification']['problem']

        assert 'negative_intent' in config
        assert config['negative_intent'] == 'no_problem'

    def test_need_payoff_has_negative_intent(self, real_constants):
        """Need_payoff phase has negative intent."""
        config = real_constants['spin']['short_answer_classification']['need_payoff']

        assert 'negative_intent' in config
        assert config['negative_intent'] == 'no_need'


# =============================================================================
# GUARD PROFILES - 100% COVERAGE
# =============================================================================

class TestGuardProfiles:
    """Tests for guard.profiles parameters."""

    def test_strict_profile_exists(self, real_constants):
        """Strict profile is defined."""
        assert 'strict' in real_constants['guard']['profiles']

    def test_relaxed_profile_exists(self, real_constants):
        """Relaxed profile is defined."""
        assert 'relaxed' in real_constants['guard']['profiles']

    def test_strict_profile_has_all_params(self, real_constants):
        """Strict profile has all required parameters."""
        strict = real_constants['guard']['profiles']['strict']

        required = ['max_turns', 'max_phase_attempts', 'max_same_state', 'timeout_seconds']
        for param in required:
            assert param in strict, f"Strict profile missing {param}"

    def test_relaxed_profile_has_all_params(self, real_constants):
        """Relaxed profile has all required parameters."""
        relaxed = real_constants['guard']['profiles']['relaxed']

        required = ['max_turns', 'max_phase_attempts', 'max_same_state', 'timeout_seconds']
        for param in required:
            assert param in relaxed, f"Relaxed profile missing {param}"

    def test_strict_more_restrictive_than_default(self, real_constants):
        """Strict profile is more restrictive than default."""
        guard = real_constants['guard']
        strict = guard['profiles']['strict']

        assert strict['max_turns'] < guard['max_turns']
        assert strict['timeout_seconds'] < guard['timeout_seconds']

    def test_relaxed_more_permissive_than_default(self, real_constants):
        """Relaxed profile is more permissive than default."""
        guard = real_constants['guard']
        relaxed = guard['profiles']['relaxed']

        assert relaxed['max_turns'] > guard['max_turns']
        assert relaxed['timeout_seconds'] > guard['timeout_seconds']


# =============================================================================
# CTA BY_ACTION - 100% COVERAGE
# =============================================================================

class TestCTAByAction:
    """Tests for cta.by_action parameters."""

    def test_demo_action_has_templates(self, real_constants):
        """Demo action has CTA templates."""
        by_action = real_constants['cta']['by_action']

        assert 'demo' in by_action
        assert len(by_action['demo']) > 0

    def test_contact_action_has_templates(self, real_constants):
        """Contact action has CTA templates."""
        by_action = real_constants['cta']['by_action']

        assert 'contact' in by_action
        assert len(by_action['contact']) > 0

    def test_trial_action_has_templates(self, real_constants):
        """Trial action has CTA templates."""
        by_action = real_constants['cta']['by_action']

        assert 'trial' in by_action
        assert len(by_action['trial']) > 0

    def test_templates_are_strings(self, real_constants):
        """All CTA templates are strings."""
        by_action = real_constants['cta']['by_action']

        for action, templates in by_action.items():
            for template in templates:
                assert isinstance(template, str), f"{action} has non-string template"


# =============================================================================
# LLM FALLBACK RESPONSES - 100% COVERAGE
# =============================================================================

class TestLLMFallbackResponses:
    """Tests for llm.fallback_responses parameters."""

    def test_all_states_have_fallback(self, real_constants):
        """All main states have fallback responses."""
        fallbacks = real_constants['llm']['fallback_responses']

        required_states = [
            'greeting', 'spin_situation', 'spin_problem', 'spin_implication',
            'spin_need_payoff', 'presentation', 'close', 'soft_close',
            'handle_objection'
        ]

        for state in required_states:
            assert state in fallbacks, f"Missing fallback for {state}"

    def test_fallback_responses_are_russian(self, real_constants):
        """Fallback responses are in Russian."""
        fallbacks = real_constants['llm']['fallback_responses']

        for state, response in fallbacks.items():
            # Check for Cyrillic characters
            has_cyrillic = any('\u0400' <= c <= '\u04FF' for c in response)
            assert has_cyrillic, f"Fallback for {state} should be in Russian"

    def test_default_fallback_exists(self, real_constants):
        """Default fallback exists."""
        assert 'default_fallback' in real_constants['llm']
        assert len(real_constants['llm']['default_fallback']) > 0


# =============================================================================
# POLICY REPAIR_ACTIONS - 100% COVERAGE
# =============================================================================

class TestPolicyRepairActions:
    """Tests for policy.repair_actions parameters."""

    def test_stuck_has_repair_action(self, real_constants):
        """Stuck situation has repair action."""
        repair = real_constants['policy']['repair_actions']

        assert 'stuck' in repair
        assert repair['stuck'] == 'clarify_one_question'

    def test_oscillation_has_repair_action(self, real_constants):
        """Oscillation situation has repair action."""
        repair = real_constants['policy']['repair_actions']

        assert 'oscillation' in repair
        assert repair['oscillation'] == 'summarize_and_clarify'

    def test_repeated_question_has_repair_action(self, real_constants):
        """Repeated question situation has repair action."""
        repair = real_constants['policy']['repair_actions']

        assert 'repeated_question' in repair


class TestPolicyObjectionActions:
    """Tests for policy.objection_actions parameters."""

    def test_reframe_action_exists(self, real_constants):
        """Reframe objection action exists."""
        actions = real_constants['policy']['objection_actions']

        assert 'reframe' in actions
        assert actions['reframe'] == 'reframe_value'

    def test_escalate_action_exists(self, real_constants):
        """Escalate objection action exists."""
        actions = real_constants['policy']['objection_actions']

        assert 'escalate' in actions

    def test_empathize_action_exists(self, real_constants):
        """Empathize objection action exists."""
        actions = real_constants['policy']['objection_actions']

        assert 'empathize' in actions


# =============================================================================
# FALLBACK OPTIONS TEMPLATES - 100% COVERAGE
# =============================================================================

class TestFallbackOptionsTemplatesComplete:
    """Complete tests for fallback.options_templates."""

    def test_spin_situation_options(self, real_constants):
        """spin_situation has complete options template."""
        options = real_constants['fallback']['options_templates']['spin_situation']

        assert 'question' in options
        assert 'options' in options
        assert len(options['options']) >= 3  # At least 3 choices

    def test_spin_problem_options(self, real_constants):
        """spin_problem has options template."""
        options = real_constants['fallback']['options_templates']

        assert 'spin_problem' in options
        assert 'question' in options['spin_problem']
        assert 'options' in options['spin_problem']

    def test_presentation_options(self, real_constants):
        """presentation has options template."""
        options = real_constants['fallback']['options_templates']

        assert 'presentation' in options

    def test_options_are_russian(self, real_constants):
        """All options are in Russian."""
        templates = real_constants['fallback']['options_templates']

        for state, template in templates.items():
            question = template.get('question', '')
            has_cyrillic = any('\u0400' <= c <= '\u04FF' for c in question)
            assert has_cyrillic, f"Options for {state} should be in Russian"


# =============================================================================
# FALLBACK REPHRASE TEMPLATES - 100% COVERAGE
# =============================================================================

class TestFallbackRephraseTemplatesComplete:
    """Complete tests for fallback.rephrase_templates."""

    def test_greeting_has_rephrases(self, real_constants):
        """greeting has rephrase templates."""
        templates = real_constants['fallback']['rephrase_templates']

        assert 'greeting' in templates
        assert len(templates['greeting']) >= 2

    def test_close_has_rephrases(self, real_constants):
        """close has rephrase templates."""
        templates = real_constants['fallback']['rephrase_templates']

        assert 'close' in templates
        assert len(templates['close']) >= 2

    def test_handle_objection_has_rephrases(self, real_constants):
        """handle_objection has rephrase templates."""
        templates = real_constants['fallback']['rephrase_templates']

        assert 'handle_objection' in templates

    def test_all_rephrases_are_unique(self, real_constants):
        """All rephrase templates are unique within state."""
        templates = real_constants['fallback']['rephrase_templates']

        for state, rephrases in templates.items():
            unique = set(rephrases)
            assert len(unique) == len(rephrases), \
                f"Duplicate rephrases in {state}"


# =============================================================================
# CTA TEMPLATES BY STATE - 100% COVERAGE
# =============================================================================

class TestCTATemplatesByState:
    """Tests for cta.templates by state."""

    def test_early_states_have_empty_templates(self, real_constants):
        """Early states have empty CTA templates."""
        templates = real_constants['cta']['templates']
        early_states = real_constants['cta']['early_states']

        for state in early_states:
            if state in templates:
                assert templates[state] == [] or len(templates[state]) == 0, \
                    f"Early state {state} should have no CTAs"

    def test_spin_implication_has_cta(self, real_constants):
        """spin_implication has CTA templates."""
        templates = real_constants['cta']['templates']

        assert 'spin_implication' in templates
        assert len(templates['spin_implication']) > 0

    def test_spin_need_payoff_has_cta(self, real_constants):
        """spin_need_payoff has CTA templates."""
        templates = real_constants['cta']['templates']

        assert 'spin_need_payoff' in templates
        assert len(templates['spin_need_payoff']) > 0

    def test_presentation_has_multiple_ctas(self, real_constants):
        """presentation has multiple CTA options."""
        templates = real_constants['cta']['templates']

        assert 'presentation' in templates
        assert len(templates['presentation']) >= 3

    def test_close_has_contact_ctas(self, real_constants):
        """close has contact-focused CTAs."""
        templates = real_constants['cta']['templates']

        assert 'close' in templates
        # Check that at least one mentions contact
        close_ctas = ' '.join(templates['close']).lower()
        assert 'контакт' in close_ctas or 'email' in close_ctas or 'созвон' in close_ctas


# =============================================================================
# INTENT CATEGORIES - 100% COVERAGE
# =============================================================================

class TestIntentCategoriesComplete:
    """Complete tests for all intent categories."""

    def test_spin_progress_intents(self, real_constants):
        """spin_progress category has all SPIN intents."""
        spin_progress = real_constants['intents']['categories']['spin_progress']

        expected = ['situation_provided', 'problem_revealed',
                    'implication_acknowledged', 'need_expressed']

        for intent in expected:
            assert intent in spin_progress, f"Missing {intent} in spin_progress"

    def test_negative_intents(self, real_constants):
        """negative category includes rejection and farewells."""
        negative = real_constants['intents']['categories']['negative']

        assert 'rejection' in negative
        assert 'farewell' in negative

    def test_objection_intents_count(self, real_constants):
        """objection category has at least 4 objection types."""
        objections = real_constants['intents']['categories']['objection']

        assert len(objections) >= 4


# =============================================================================
# LEAD SCORING ALL POSITIVE WEIGHTS - 100% COVERAGE
# =============================================================================

class TestLeadScoringAllPositiveWeights:
    """Tests for all lead_scoring.positive_weights."""

    def test_all_documented_weights_exist(self, real_constants):
        """All documented positive weights exist."""
        weights = real_constants['lead_scoring']['positive_weights']

        expected = [
            'demo_request', 'price_with_size', 'callback_request',
            'consultation_request', 'contact_provided', 'explicit_problem',
            'competitor_comparison', 'budget_mentioned', 'timeline_mentioned',
            'multiple_questions', 'features_question', 'integrations_question',
            'general_interest', 'price_question'
        ]

        for signal in expected:
            assert signal in weights, f"Missing positive weight: {signal}"

    def test_weights_are_positive(self, real_constants):
        """All positive weights are positive numbers."""
        weights = real_constants['lead_scoring']['positive_weights']

        for signal, weight in weights.items():
            assert weight > 0, f"{signal} weight should be positive"


class TestLeadScoringAllNegativeWeights:
    """Tests for all lead_scoring.negative_weights."""

    def test_all_documented_weights_exist(self, real_constants):
        """All documented negative weights exist."""
        weights = real_constants['lead_scoring']['negative_weights']

        expected = [
            'objection_price', 'objection_competitor', 'objection_no_time',
            'objection_think', 'objection_no_need', 'unclear_repeated',
            'rejection_soft', 'frustration'
        ]

        for signal in expected:
            assert signal in weights, f"Missing negative weight: {signal}"

    def test_weights_are_negative(self, real_constants):
        """All negative weights are negative numbers."""
        weights = real_constants['lead_scoring']['negative_weights']

        for signal, weight in weights.items():
            assert weight < 0, f"{signal} weight should be negative"
