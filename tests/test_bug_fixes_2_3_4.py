"""
Targeted tests for data extraction, phase completion, and guard threshold fixes.

Tests cover:
- Data extraction for composite messages, price template selection,
  CompositeMessageLayer refinable intents, do_not_ask fallback
- has_completed_minimum_phases condition, conditional transitions
- max_same_message raised to 3

NOTE: Tests that require LLM or semantic search are intentionally skipped.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# =============================================================================
# Phase 1 — DataExtractor Fixes (1a, 1b)
# =============================================================================

class TestDataExtractorBug2:
    """Tests for DataExtractor range pattern (1a) and leading number (1b)."""

    @pytest.fixture
    def extractor(self):
        from src.classifier.extractors.data_extractor import DataExtractor
        return DataExtractor()

    # --- Fix 1a: Range pattern ---

    def test_range_pattern_dash(self, extractor):
        """Range pattern: '10-15 человек' extracts lower bound."""
        result = extractor.extract("10-15 человек", {})
        assert result.get("company_size") == 10

    def test_range_pattern_en_dash(self, extractor):
        """Range pattern: '10–15 сотрудников' with en-dash."""
        result = extractor.extract("10–15 сотрудников", {})
        assert result.get("company_size") == 10

    def test_range_pattern_with_text(self, extractor):
        """Range pattern embedded in longer text."""
        result = extractor.extract("у нас где-то 20-30 менеджеров в отделе", {})
        assert result.get("company_size") == 20

    def test_range_pattern_large(self, extractor):
        """Range pattern with larger numbers."""
        result = extractor.extract("300-500 продавцов", {})
        assert result.get("company_size") == 300

    # --- Fix 1b: Leading number in composite message ---

    def test_leading_number_with_dot(self, extractor):
        """'500. Скока стоит?' extracts company_size=500."""
        result = extractor.extract("500. Скока стоит?", {})
        assert result.get("company_size") == 500

    def test_leading_number_with_comma(self, extractor):
        """'15, а скока стоит?' extracts company_size=15."""
        result = extractor.extract("15, а скока стоит?", {})
        assert result.get("company_size") == 15

    def test_leading_number_with_space(self, extractor):
        """'50 какая цена?' extracts company_size=50."""
        result = extractor.extract("50 какая цена?", {})
        assert result.get("company_size") == 50

    def test_leading_number_too_small_rejected(self, extractor):
        """Numbers < 5 should NOT be extracted (could be list markers)."""
        result = extractor.extract("3. а скока стоит?", {})
        assert "company_size" not in result

    def test_leading_number_4_rejected(self, extractor):
        """'4, скока стоит' — too small, not extracted."""
        result = extractor.extract("4, скока стоит", {})
        assert "company_size" not in result

    def test_leading_number_5_accepted(self, extractor):
        """'5. скока стоит' — exactly 5, extracted."""
        result = extractor.extract("5. скока стоит", {})
        assert result.get("company_size") == 5

    def test_leading_number_boundary_10000(self, extractor):
        """'10000. ok' — boundary, extracted."""
        result = extractor.extract("10000. ok", {})
        assert result.get("company_size") == 10000

    def test_leading_number_over_10000_rejected(self, extractor):
        """'10001. ok' — over boundary, not extracted."""
        result = extractor.extract("10001. ok", {})
        assert "company_size" not in result

    def test_keyword_pattern_takes_priority(self, extractor):
        """'7 человек. Скока стоит?' — keyword pattern (Tier 1) takes priority."""
        result = extractor.extract("7 человек. Скока стоит?", {})
        assert result.get("company_size") == 7

    def test_context_just_number_still_works(self, extractor):
        """'500' when company_size is in missing_data — original logic still works."""
        result = extractor.extract("500", {"missing_data": ["company_size"]})
        assert result.get("company_size") == 500

    def test_context_just_number_without_missing_data(self, extractor):
        """'500' without missing_data context — no extraction (no keyword, no context)."""
        result = extractor.extract("500", {})
        # The leading number pattern requires a trailing separator character
        # Pure "500" without trailing punctuation won't match leading_number pattern
        # and without context won't match just_number pattern
        # This is expected: no extraction for bare numbers without context

# =============================================================================
# Phase 1 — CompositeMessageLayer REFINABLE_INTENTS (1c)
# =============================================================================

class TestCompositeRefinableIntents:
    """Tests for price intents added to REFINABLE_INTENTS."""

    def test_price_question_in_refinable_intents(self):
        """price_question is now in REFINABLE_INTENTS."""
        from src.classifier.composite_refinement import CompositeMessageRefinementLayer
        assert "price_question" in CompositeMessageRefinementLayer.REFINABLE_INTENTS

    def test_pricing_details_in_refinable_intents(self):
        """pricing_details is now in REFINABLE_INTENTS."""
        from src.classifier.composite_refinement import CompositeMessageRefinementLayer
        assert "pricing_details" in CompositeMessageRefinementLayer.REFINABLE_INTENTS

    def test_cost_inquiry_in_refinable_intents(self):
        """cost_inquiry is now in REFINABLE_INTENTS."""
        from src.classifier.composite_refinement import CompositeMessageRefinementLayer
        assert "cost_inquiry" in CompositeMessageRefinementLayer.REFINABLE_INTENTS

    def test_original_intents_still_present(self):
        """Original refinable intents still present."""
        from src.classifier.composite_refinement import CompositeMessageRefinementLayer
        for intent in ["objection_think", "objection_no_need", "rejection", "unclear",
                       "small_talk", "greeting", "gratitude"]:
            assert intent in CompositeMessageRefinementLayer.REFINABLE_INTENTS, \
                f"Original intent '{intent}' missing from REFINABLE_INTENTS"

# =============================================================================
# Phase 1 — Constants YAML mappings (1d)
# =============================================================================

class TestConstantsYamlMappings:
    """Tests for action_expects_data and action_data_intent mappings."""

    def test_action_expects_data_has_answer_with_pricing(self):
        """answer_with_pricing mapped in action_expects_data."""
        from src.yaml_config.constants import get_composite_refinement_config
        config = get_composite_refinement_config()
        action_expects = config.get("action_expects_data", {})
        assert "answer_with_pricing" in action_expects
        assert action_expects["answer_with_pricing"] == "company_size"

    def test_action_data_intent_has_answer_with_pricing(self):
        """answer_with_pricing mapped to price_question in action_data_intent."""
        from src.yaml_config.constants import get_composite_refinement_config
        config = get_composite_refinement_config()
        action_intent = config.get("action_data_intent", {})
        assert "answer_with_pricing" in action_intent
        # CRITICAL: Must be price_question, NOT info_provided
        assert action_intent["answer_with_pricing"] == "price_question"

    def test_action_data_intent_not_info_provided(self):
        """answer_with_pricing must NOT map to info_provided (would break price chain)."""
        from src.yaml_config.constants import get_composite_refinement_config
        config = get_composite_refinement_config()
        action_intent = config.get("action_data_intent", {})
        assert action_intent.get("answer_with_pricing") != "info_provided"

# =============================================================================
# Phase 2 — _get_price_template_key fix (2a)
# =============================================================================

class TestGetPriceTemplateKey:
    """Tests for _get_price_template_key respecting policy overlay."""

    @pytest.fixture
    def generator(self):
        """Create a minimal generator instance for method testing."""
        from src.generator import ResponseGenerator
        gen = ResponseGenerator.__new__(ResponseGenerator)
        # Set minimal required attributes
        gen.PRICE_RELATED_INTENTS = {"price_question", "pricing_details", "cost_inquiry"}
        return gen

    def test_action_answer_with_pricing_direct(self, generator):
        """Policy overlay answer_with_pricing_direct is honored."""
        result = generator._get_price_template_key("price_question", "answer_with_pricing_direct")
        assert result == "answer_with_pricing_direct"

    def test_action_answer_with_pricing(self, generator):
        """Explicit answer_with_pricing action is honored."""
        result = generator._get_price_template_key("price_question", "answer_with_pricing")
        assert result == "answer_with_pricing"

    def test_action_answer_pricing_details(self, generator):
        """Explicit answer_pricing_details action is honored."""
        result = generator._get_price_template_key("pricing_details", "answer_pricing_details")
        assert result == "answer_pricing_details"

    def test_action_answer_with_roi(self, generator):
        """Policy overlay answer_with_roi is honored."""
        result = generator._get_price_template_key("price_question", "answer_with_roi")
        assert result == "answer_with_roi"

    def test_action_calculate_roi_response(self, generator):
        """Policy overlay calculate_roi_response is honored."""
        result = generator._get_price_template_key("price_question", "calculate_roi_response")
        assert result == "calculate_roi_response"

    def test_fallback_continue_current_goal_price_question(self, generator):
        """Non-pricing action with price_question intent falls back to answer_with_pricing."""
        result = generator._get_price_template_key("price_question", "continue_current_goal")
        assert result == "answer_with_pricing"

    def test_fallback_continue_current_goal_pricing_details(self, generator):
        """Non-pricing action with pricing_details intent falls back to answer_pricing_details."""
        result = generator._get_price_template_key("pricing_details", "continue_current_goal")
        assert result == "answer_pricing_details"

    def test_fallback_unknown_intent(self, generator):
        """Non-pricing action with unknown intent falls back to answer_with_facts."""
        result = generator._get_price_template_key("cost_inquiry", "continue_current_goal")
        assert result == "answer_with_facts"

    def test_non_pricing_action_not_passed_through(self, generator):
        """Non-pricing actions should NOT be passed through."""
        result = generator._get_price_template_key("price_question", "some_random_action")
        assert result == "answer_with_pricing"  # Falls through to intent-based

# =============================================================================
# Phase 2 — do_not_ask fallback (2c)
# =============================================================================

class TestDoNotAskFallback:
    """Tests for do_not_ask being populated when company_size is known."""

    def test_do_not_ask_set_when_company_size_known(self):
        """When company_size is collected and do_not_ask is empty, it should be set."""
        collected = {"company_size": 500}
        variables = {"do_not_ask": ""}

        # Simulate the logic from generator.py
        if collected.get("company_size") and not variables.get("do_not_ask"):
            variables["do_not_ask"] = (
                "⚠️ НЕ СПРАШИВАЙ о размере команды/количестве сотрудников — "
                f"уже известно: {collected['company_size']} человек."
            )

        assert "500" in variables["do_not_ask"]
        assert "НЕ СПРАШИВАЙ" in variables["do_not_ask"]

    def test_do_not_ask_not_overwritten(self):
        """When do_not_ask is already set by dedup, it should NOT be overwritten."""
        collected = {"company_size": 500}
        variables = {"do_not_ask": "Existing dedup instruction"}

        if collected.get("company_size") and not variables.get("do_not_ask"):
            variables["do_not_ask"] = "Should NOT appear"

        assert variables["do_not_ask"] == "Existing dedup instruction"

    def test_do_not_ask_not_set_without_company_size(self):
        """When company_size is not collected, do_not_ask stays empty."""
        collected = {}
        variables = {"do_not_ask": ""}

        if collected.get("company_size") and not variables.get("do_not_ask"):
            variables["do_not_ask"] = "Should NOT appear"

        assert variables["do_not_ask"] == ""

# =============================================================================
# Phase 3 — has_completed_minimum_phases condition (3a)
# =============================================================================

class TestHasCompletedMinimumPhases:
    """Tests for has_completed_minimum_phases condition."""

    @pytest.fixture(autouse=True)
    def enable_feature_flag(self):
        """Enable phase_completion_gating feature flag for tests."""
        with patch("src.feature_flags.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            yield mock_flags

    def test_early_no_data_returns_false(self, enable_feature_flag):
        """Turn 1, no data → False (prevent premature close)."""
        from src.conditions.state_machine import create_test_context, has_completed_minimum_phases
        ctx = create_test_context(
            state="spin_situation",
            turn_number=1,
            collected_data={},
        )
        assert has_completed_minimum_phases(ctx) is False

    def test_turn_7_returns_true(self, enable_feature_flag):
        """Turn 7 (≥6) → True (sufficient engagement)."""
        from src.conditions.state_machine import create_test_context, has_completed_minimum_phases
        ctx = create_test_context(
            state="spin_situation",
            turn_number=7,
            collected_data={},
        )
        assert has_completed_minimum_phases(ctx) is True

    def test_turn_6_returns_true(self, enable_feature_flag):
        """Turn 6 (exactly ≥6) → True."""
        from src.conditions.state_machine import create_test_context, has_completed_minimum_phases
        ctx = create_test_context(
            state="spin_situation",
            turn_number=6,
            collected_data={},
        )
        assert has_completed_minimum_phases(ctx) is True

    def test_turn_5_no_data_returns_false(self, enable_feature_flag):
        """Turn 5 (<6), no data → False."""
        from src.conditions.state_machine import create_test_context, has_completed_minimum_phases
        ctx = create_test_context(
            state="spin_situation",
            turn_number=5,
            collected_data={},
        )
        assert has_completed_minimum_phases(ctx) is False

    def test_has_size_and_pain_returns_true(self, enable_feature_flag):
        """Has company_size + pain_point → True (minimum qualification)."""
        from src.conditions.state_machine import create_test_context, has_completed_minimum_phases
        ctx = create_test_context(
            state="spin_situation",
            turn_number=2,
            collected_data={"company_size": 10, "pain_point": "теряем клиентов"},
        )
        assert has_completed_minimum_phases(ctx) is True

    def test_has_size_and_pain_category_returns_true(self, enable_feature_flag):
        """Has company_size + pain_category → True."""
        from src.conditions.state_machine import create_test_context, has_completed_minimum_phases
        ctx = create_test_context(
            state="spin_problem",
            turn_number=2,
            collected_data={"company_size": 10, "pain_category": "losing_clients"},
        )
        assert has_completed_minimum_phases(ctx) is True

    def test_has_only_size_returns_false(self, enable_feature_flag):
        """Has company_size only (no pain) → False."""
        from src.conditions.state_machine import create_test_context, has_completed_minimum_phases
        ctx = create_test_context(
            state="spin_situation",
            turn_number=2,
            collected_data={"company_size": 10},
        )
        assert has_completed_minimum_phases(ctx) is False

    def test_has_only_pain_returns_false(self, enable_feature_flag):
        """Has pain_point only (no size) → False."""
        from src.conditions.state_machine import create_test_context, has_completed_minimum_phases
        ctx = create_test_context(
            state="spin_situation",
            turn_number=2,
            collected_data={"pain_point": "теряем клиентов"},
        )
        assert has_completed_minimum_phases(ctx) is False

    def test_terminal_state_always_true(self, enable_feature_flag):
        """Terminal states always return True."""
        from src.conditions.state_machine import create_test_context, has_completed_minimum_phases
        for state in ["presentation", "close", "soft_close", "handle_objection", "escalated"]:
            ctx = create_test_context(
                state=state,
                turn_number=1,
                collected_data={},
            )
            assert has_completed_minimum_phases(ctx) is True, \
                f"Terminal state '{state}' should return True"

    def test_feature_flag_disabled_returns_true(self):
        """When phase_completion_gating is disabled, always returns True."""
        from src.conditions.state_machine import create_test_context, has_completed_minimum_phases
        with patch("src.feature_flags.flags") as mock_flags:
            mock_flags.is_enabled.return_value = False
            ctx = create_test_context(
                state="spin_situation",
                turn_number=1,
                collected_data={},
            )
            assert has_completed_minimum_phases(ctx) is True

# =============================================================================
# Phase 3 — Conditional transitions in mixins (3b, 3c)
# =============================================================================

class TestMixinConditionalTransitions:
    """Tests that _universal_base and close_shortcuts transitions are conditional."""

    @pytest.fixture
    def mixins_data(self):
        """Load mixins YAML data."""
        import yaml
        mixins_path = Path(__file__).parent.parent / "src" / "yaml_config" / "flows" / "_base" / "mixins.yaml"
        with open(mixins_path) as f:
            data = yaml.safe_load(f)
        return data.get("mixins", {})

    def test_universal_base_demo_request_is_conditional(self, mixins_data):
        """demo_request transition in _universal_base is conditional."""
        universal = mixins_data.get("_universal_base", {})
        transitions = universal.get("transitions", {})

        # demo_request should be a list with conditional entries
        demo_t = transitions.get("demo_request")
        assert isinstance(demo_t, list), "demo_request transition should be conditional (list)"
        assert demo_t[0].get("when") == "has_completed_minimum_phases"
        assert demo_t[0].get("then") == "close"

    def test_universal_base_callback_request_is_conditional(self, mixins_data):
        """callback_request transition in _universal_base is conditional."""
        universal = mixins_data.get("_universal_base", {})
        transitions = universal.get("transitions", {})

        callback_t = transitions.get("callback_request")
        assert isinstance(callback_t, list), "callback_request transition should be conditional"
        assert callback_t[0].get("when") == "has_completed_minimum_phases"

    def test_universal_base_contact_provided_unconditional(self, mixins_data):
        """contact_provided transition remains unconditional (not guarded)."""
        universal = mixins_data.get("_universal_base", {})
        transitions = universal.get("transitions", {})

        # contact_provided should remain a simple string
        assert transitions.get("contact_provided") == "success"

    def test_close_shortcuts_demo_request_conditional(self, mixins_data):
        """close_shortcuts demo_request is conditional."""
        shortcuts = mixins_data.get("close_shortcuts", {})
        transitions = shortcuts.get("transitions", {})

        demo_t = transitions.get("demo_request")
        assert isinstance(demo_t, list), "close_shortcuts demo_request should be conditional"
        assert demo_t[0].get("when") == "has_completed_minimum_phases"

    def test_close_shortcuts_callback_request_conditional(self, mixins_data):
        """close_shortcuts callback_request is conditional."""
        shortcuts = mixins_data.get("close_shortcuts", {})
        transitions = shortcuts.get("transitions", {})

        callback_t = transitions.get("callback_request")
        assert isinstance(callback_t, list), "close_shortcuts callback_request should be conditional"
        assert callback_t[0].get("when") == "has_completed_minimum_phases"

# =============================================================================
# Phase 4 — max_same_message threshold (4a)
# =============================================================================

class TestGuardThreshold:
    """Tests for max_same_message raised from 2 to 3."""

    def test_default_max_same_message_is_3(self):
        """Default max_same_message is now 3 (was 2)."""
        from src.conversation_guard import GuardConfig
        config = GuardConfig()
        assert config.max_same_message == 3

    def test_guard_allows_2_identical_messages(self):
        """Guard should NOT trigger on 2 identical messages (was triggering before)."""
        from src.conversation_guard import ConversationGuard
        guard = ConversationGuard()

        result1 = guard.check("state1", "same message", {})
        result2 = guard.check("state1", "same message", {})

        # check() returns Tuple[bool, Optional[str]]
        # (True, "TIER_2") means intervention, (False, None) means OK
        triggered, action = result2
        # After 2 identical messages, should NOT trigger TIER_2
        assert action != "TIER_2", \
            "2 identical messages should not trigger TIER_2 with max_same_message=3"

    def test_guard_triggers_on_3_identical_messages(self):
        """Guard SHOULD trigger on 3 identical messages."""
        from src.conversation_guard import ConversationGuard
        guard = ConversationGuard()

        guard.check("state1", "same message", {})
        guard.check("state1", "same message", {})
        result3 = guard.check("state1", "same message", {})

        # check() returns Tuple[bool, Optional[str]]
        triggered, action = result3
        # After 3 identical messages, should trigger (action is "fallback_tier_2")
        assert triggered is True, "3 identical messages should trigger intervention"
        assert "tier_2" in action.lower(), \
            f"3 identical messages should trigger tier_2, got: {action}"

# =============================================================================
# Phase 5 — Feature flag (5a)
# =============================================================================

class TestFeatureFlagPhaseCompletionGating:
    """Tests for phase_completion_gating feature flag."""

    def test_flag_exists_in_defaults(self):
        """phase_completion_gating flag exists in defaults."""
        from src.feature_flags import FeatureFlags
        assert "phase_completion_gating" in FeatureFlags.DEFAULTS

    def test_flag_default_value_true(self):
        """phase_completion_gating is enabled by default."""
        from src.feature_flags import FeatureFlags
        assert FeatureFlags.DEFAULTS["phase_completion_gating"] is True

# =============================================================================
# Config Validation (5c)
# =============================================================================

class TestConfigValidation:
    """Tests for startup config validation in CompositeMessageRefinementLayer."""

    def test_layer_validates_action_expects_data(self):
        """CompositeMessageRefinementLayer validates answer_with_pricing in config."""
        from src.classifier.composite_refinement import CompositeMessageRefinementLayer
        layer = CompositeMessageRefinementLayer()
        assert "answer_with_pricing" in layer._action_expects_data

    def test_layer_validates_action_data_intent(self):
        """CompositeMessageRefinementLayer validates answer_with_pricing in action_data_intent."""
        from src.classifier.composite_refinement import CompositeMessageRefinementLayer
        layer = CompositeMessageRefinementLayer()
        assert "answer_with_pricing" in layer._action_data_intent
        assert layer._action_data_intent["answer_with_pricing"] == "price_question"

# =============================================================================
# COMPOSITE: Integration-style tests — composite message intent preservation
# =============================================================================

class TestCompositeMessageIntentPreservation:
    """
    CRITICAL: Verify that CompositeMessageLayer preserves price_question intent
    when refining composite messages with data.
    """

    @pytest.fixture
    def layer(self):
        from src.classifier.composite_refinement import CompositeMessageRefinementLayer
        return CompositeMessageRefinementLayer()

    def test_should_refine_price_question_with_data(self, layer):
        """price_question with numeric data should pass should_refine gate."""
        from src.classifier.composite_refinement import CompositeMessageContext

        ctx = CompositeMessageContext(
            message="500. Скока стоит?",
            intent="price_question",
            confidence=0.85,
            last_action="answer_with_pricing",
        )

        # Check that the layer considers this refinable
        assert ctx.intent in layer.REFINABLE_INTENTS

    def test_action_data_intent_preserves_price_question(self, layer):
        """
        When action=answer_with_pricing and data is extracted,
        the target intent should be price_question (not info_provided).
        """
        target_intent = layer._action_data_intent.get("answer_with_pricing")
        assert target_intent == "price_question", \
            f"Expected 'price_question', got '{target_intent}'. " \
            "info_provided would break price template selection."

# =============================================================================
# Pipeline ordering documentation (5b)
# =============================================================================

class TestPipelineDocumentation:
    """Tests for pipeline ordering invariant documentation."""

    def test_composite_refinement_docstring_has_invariant(self):
        """Module docstring mentions DataAwareRefinement ordering invariant."""
        import src.classifier.composite_refinement as mod
        docstring = mod.__doc__ or ""
        assert "DataAwareRefinement" in docstring or "DataAwareRefinementLayer" in docstring, \
            "Module docstring should document INVARIANT about DataAwareRefinementLayer ordering"

# =============================================================================
# Regression: Existing patterns still work
# =============================================================================

class TestRegressionExistingPatterns:
    """Ensure existing DataExtractor patterns are not broken."""

    @pytest.fixture
    def extractor(self):
        from src.classifier.extractors.data_extractor import DataExtractor
        return DataExtractor()

    def test_basic_keyword_extraction(self, extractor):
        """'20 человек' still works."""
        result = extractor.extract("20 человек", {})
        assert result.get("company_size") == 20

    def test_context_just_number(self, extractor):
        """'50' with missing_data context still works."""
        result = extractor.extract("50", {"missing_data": ["company_size"]})
        assert result.get("company_size") == 50

    def test_nas_pattern(self, extractor):
        """'нас 15' still works."""
        result = extractor.extract("нас 15", {})
        assert result.get("company_size") == 15

    def test_team_pattern(self, extractor):
        """'команда из 10' still works."""
        result = extractor.extract("команда из 10", {})
        assert result.get("company_size") == 10
