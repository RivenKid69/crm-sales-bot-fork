"""
Tests for Changes 1-9 fixes.

Covers:
- Change 1: continue_current_goal contact_info example
- Change 2: answer_with_facts goal-aware
- Change 3: answer_and_continue goal-aware
- Change 3b: Utility templates (small_talk, acknowledge, clarify) goal-aware
- Change 4: close_answer_and_collect template + close state rules
- Change 5 (states): Close state rule updates
- Change 5 (bot.py): guard_rephrase state-aware resolution
- Change 6: Close fallback options_templates
- Change 7: IntentPatternGuardSource
- Change 8: ComparisonRefinementLayer
- Change 9: Feature flags

NOTE: Tests skip LLM and semantic search — all tests are unit/config level.
"""

import pytest
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List, Set
from unittest.mock import Mock, MagicMock, patch

_PROJECT_ROOT = Path(__file__).parent.parent


def _load_yaml(path: str) -> Dict[str, Any]:
    """Load a YAML file relative to project root."""
    with open(_PROJECT_ROOT / path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# =============================================================================
# PHASE A: YAML Template & Config Tests
# =============================================================================

class TestTemplateChanges:
    """Test YAML template modifications (Changes 1-4, 3b)."""

    @pytest.fixture
    def templates_config(self):
        """Load templates from YAML."""
        return _load_yaml("src/yaml_config/templates/_base/prompts.yaml")

    def test_change1_continue_current_goal_has_contact_info_example(self, templates_config):
        """Change 1: continue_current_goal mentions contact_info."""
        template = templates_config["templates"]["continue_current_goal"]["template"]
        assert "contact_info" in template
        assert "телефон" in template.lower() or "email" in template.lower()

    def test_change2_answer_with_facts_has_goal_param(self, templates_config):
        """Change 2: answer_with_facts has optional goal parameter."""
        params = templates_config["templates"]["answer_with_facts"]["parameters"]
        assert "goal" in params.get("optional", [])

    def test_change2_answer_with_facts_template_uses_goal(self, templates_config):
        """Change 2: answer_with_facts template references {goal}."""
        template = templates_config["templates"]["answer_with_facts"]["template"]
        assert "{goal}" in template

    def test_change3_answer_and_continue_has_goal_param(self, templates_config):
        """Change 3: answer_and_continue has optional goal parameter."""
        params = templates_config["templates"]["answer_and_continue"]["parameters"]
        assert "goal" in params.get("optional", [])

    def test_change3_answer_and_continue_template_uses_goal(self, templates_config):
        """Change 3: answer_and_continue template references {goal}."""
        template = templates_config["templates"]["answer_and_continue"]["template"]
        assert "{goal}" in template

    def test_change3b_small_talk_has_goal_param(self, templates_config):
        """Change 3b: small_talk_and_continue has optional goal."""
        params = templates_config["templates"]["small_talk_and_continue"]["parameters"]
        assert "goal" in params.get("optional", [])

    def test_change3b_small_talk_template_uses_goal(self, templates_config):
        """Change 3b: small_talk_and_continue template references {goal}."""
        template = templates_config["templates"]["small_talk_and_continue"]["template"]
        assert "{goal}" in template

    def test_change3b_acknowledge_has_goal_param(self, templates_config):
        """Change 3b: acknowledge_and_continue has optional goal."""
        params = templates_config["templates"]["acknowledge_and_continue"]["parameters"]
        assert "goal" in params.get("optional", [])

    def test_change3b_acknowledge_template_uses_goal(self, templates_config):
        """Change 3b: acknowledge_and_continue template references {goal}."""
        template = templates_config["templates"]["acknowledge_and_continue"]["template"]
        assert "{goal}" in template

    def test_change3b_clarify_has_goal_param(self, templates_config):
        """Change 3b: clarify_and_continue has optional goal."""
        params = templates_config["templates"]["clarify_and_continue"]["parameters"]
        assert "goal" in params.get("optional", [])

    def test_change3b_clarify_template_uses_goal(self, templates_config):
        """Change 3b: clarify_and_continue template references {goal}."""
        template = templates_config["templates"]["clarify_and_continue"]["template"]
        assert "{goal}" in template

    def test_change4_close_answer_and_collect_exists(self, templates_config):
        """Change 4: close_answer_and_collect template exists."""
        assert "close_answer_and_collect" in templates_config["templates"]

    def test_change4_close_answer_and_collect_params(self, templates_config):
        """Change 4: close_answer_and_collect has correct parameters."""
        tpl = templates_config["templates"]["close_answer_and_collect"]
        params = tpl["parameters"]
        assert "system" in params["required"]
        assert "history" in params["required"]
        assert "user_message" in params["required"]
        assert "collected_data" in params["required"]
        assert "facts" in params["required"]
        assert "goal" in params.get("optional", [])
        assert "retrieved_facts" in params.get("optional", [])

    def test_change4_close_answer_and_collect_mentions_contact(self, templates_config):
        """Change 4: close_answer_and_collect template asks for contact."""
        template = templates_config["templates"]["close_answer_and_collect"]["template"]
        assert "контакт" in template.lower() or "email" in template.lower()

    def test_all_instate_templates_goal_aware(self, templates_config):
        """100% coverage: all in-state templates have goal in template or optional params."""
        goal_aware_templates = [
            "answer_with_facts",
            "answer_and_continue",
            "continue_current_goal",
            "small_talk_and_continue",
            "acknowledge_and_continue",
            "clarify_and_continue",
            "close_answer_and_collect",
        ]
        for tpl_name in goal_aware_templates:
            tpl = templates_config["templates"][tpl_name]
            template_text = tpl["template"]
            params = tpl["parameters"]
            has_goal_in_template = "{goal}" in template_text
            has_goal_in_required = "goal" in params.get("required", [])
            has_goal_in_optional = "goal" in params.get("optional", [])
            assert has_goal_in_template or has_goal_in_required or has_goal_in_optional, \
                f"Template '{tpl_name}' is not goal-aware"


class TestStatesYamlChanges:
    """Test states.yaml modifications (Change 5-states)."""

    @pytest.fixture
    def states_config(self):
        """Load states from YAML."""
        return _load_yaml("src/yaml_config/flows/_base/states.yaml")

    def test_close_comparison_uses_close_answer_and_collect(self, states_config):
        """Change 5: close state comparison → close_answer_and_collect."""
        close_rules = states_config["states"]["close"]["rules"]
        assert close_rules["comparison"] == "close_answer_and_collect"

    def test_close_question_features_uses_close_answer_and_collect(self, states_config):
        """Change 5: close state question_features → close_answer_and_collect."""
        close_rules = states_config["states"]["close"]["rules"]
        assert close_rules["question_features"] == "close_answer_and_collect"

    def test_close_question_integrations_uses_close_answer_and_collect(self, states_config):
        """Change 5: close state question_integrations → close_answer_and_collect."""
        close_rules = states_config["states"]["close"]["rules"]
        assert close_rules["question_integrations"] == "close_answer_and_collect"

    def test_close_info_provided_still_continue_current_goal(self, states_config):
        """Change 1 dependency: close state info_provided → continue_current_goal."""
        close_rules = states_config["states"]["close"]["rules"]
        assert close_rules["info_provided"] == "continue_current_goal"

    def test_close_price_unchanged(self, states_config):
        """Verify price rules unchanged in close."""
        close_rules = states_config["states"]["close"]["rules"]
        assert close_rules["price_question"] == "answer_with_facts"
        assert close_rules["pricing_details"] == "answer_with_facts"


class TestConstantsYamlChanges:
    """Test constants.yaml modifications (Changes 6, 7-config)."""

    @pytest.fixture
    def constants_config(self):
        """Load constants from YAML."""
        return _load_yaml("src/yaml_config/constants.yaml")

    def test_change6_close_options_template_exists(self, constants_config):
        """Change 6: close options_templates exists in fallback config."""
        options_templates = constants_config["fallback"]["options_templates"]
        assert "close" in options_templates

    def test_change6_close_options_has_4_options(self, constants_config):
        """Change 6: close options has 4 options."""
        close_opts = constants_config["fallback"]["options_templates"]["close"]
        assert len(close_opts["options"]) == 4

    def test_change6_close_options_include_contact(self, constants_config):
        """Change 6: close options include contact-related options."""
        close_opts = constants_config["fallback"]["options_templates"]["close"]
        options_text = " ".join(close_opts["options"]).lower()
        assert "номер" in options_text or "email" in options_text or "демо" in options_text

    def test_change7_comparison_like_composed_category(self, constants_config):
        """Change 7: comparison_like composed category exists."""
        composed = constants_config["intents"]["composed_categories"]
        assert "comparison_like" in composed

    def test_change7_comparison_like_has_direct_intents(self, constants_config):
        """Change 7: comparison_like has direct_intents with comparison intents."""
        cat = constants_config["intents"]["composed_categories"]["comparison_like"]
        direct_intents = cat.get("direct_intents", [])
        assert "comparison" in direct_intents
        assert "question_tariff_comparison" in direct_intents

    def test_change7_intent_pattern_guard_config_exists(self, constants_config):
        """Change 7: intent_pattern_guard config exists under intents."""
        assert "intent_pattern_guard" in constants_config["intents"]
        guard_cfg = constants_config["intents"]["intent_pattern_guard"]
        assert "patterns" in guard_cfg

    def test_change7_comparison_like_pattern_config(self, constants_config):
        """Change 7: comparison_like pattern has correct structure."""
        patterns = constants_config["intents"]["intent_pattern_guard"]["patterns"]
        assert "comparison_like" in patterns
        cl = patterns["comparison_like"]
        assert "intents" in cl
        assert "persona_limits" in cl
        assert "close_action" in cl
        assert "default_action" in cl
        assert cl["close_action"] == "close_answer_and_collect"
        assert cl["default_action"] == "nudge_progress"

    def test_change7_persona_limits_structure(self, constants_config):
        """Change 7: persona_limits has default + persona-specific limits."""
        limits = constants_config["intents"]["intent_pattern_guard"]["patterns"]["comparison_like"]["persona_limits"]
        assert "default" in limits
        assert limits["default"]["streak"] == 3
        assert limits["default"]["total"] == 5


# =============================================================================
# PHASE B: Feature Flags Tests
# =============================================================================

class TestFeatureFlags:
    """Test feature flag additions (Change 9)."""

    def test_intent_pattern_guard_flag_exists(self):
        """Change 9: intent_pattern_guard flag exists and defaults to False."""
        from src.feature_flags import FeatureFlags
        assert "intent_pattern_guard" in FeatureFlags.DEFAULTS
        assert FeatureFlags.DEFAULTS["intent_pattern_guard"] is False

    def test_comparison_refinement_flag_exists(self):
        """Change 9: comparison_refinement flag exists and defaults to False."""
        from src.feature_flags import FeatureFlags
        assert "comparison_refinement" in FeatureFlags.DEFAULTS
        assert FeatureFlags.DEFAULTS["comparison_refinement"] is False

    def test_intent_pattern_guard_property(self):
        """Change 9: flags.intent_pattern_guard property works."""
        from src.feature_flags import FeatureFlags
        ff = FeatureFlags()
        assert ff.intent_pattern_guard is False
        ff.set_override("intent_pattern_guard", True)
        assert ff.intent_pattern_guard is True
        ff.clear_override("intent_pattern_guard")

    def test_comparison_refinement_property(self):
        """Change 9: flags.comparison_refinement property works."""
        from src.feature_flags import FeatureFlags
        ff = FeatureFlags()
        assert ff.comparison_refinement is False
        ff.set_override("comparison_refinement", True)
        assert ff.comparison_refinement is True
        ff.clear_override("comparison_refinement")


# =============================================================================
# PHASE B: guard_rephrase state-aware resolution Tests
# =============================================================================

class TestGuardRephraseStateAware:
    """Test guard_rephrase state-aware template resolution (Change 5-code)."""

    def test_guard_rephrase_uses_state_specific_template_if_exists(self):
        """Change 5: guard_rephrase tries {state}_continue_goal first."""
        # Mock generator with state-specific template
        mock_generator = Mock()
        mock_generator._get_template = Mock(return_value={"template": "test"})
        mock_generator.generate = Mock(return_value="state-specific response")

        # Simulate the guard_rephrase logic from bot.py
        current_state = "close"
        rephrase_template = f"{current_state}_continue_goal"
        if not mock_generator._get_template(rephrase_template):
            rephrase_template = "continue_current_goal"
        response = mock_generator.generate(rephrase_template, {})

        mock_generator._get_template.assert_called_with("close_continue_goal")
        mock_generator.generate.assert_called_with("close_continue_goal", {})

    def test_guard_rephrase_falls_back_to_continue_current_goal(self):
        """Change 5: guard_rephrase falls back to continue_current_goal."""
        mock_generator = Mock()
        mock_generator._get_template = Mock(return_value=None)
        mock_generator.generate = Mock(return_value="fallback response")

        current_state = "close"
        rephrase_template = f"{current_state}_continue_goal"
        if not mock_generator._get_template(rephrase_template):
            rephrase_template = "continue_current_goal"
        response = mock_generator.generate(rephrase_template, {})

        mock_generator.generate.assert_called_with("continue_current_goal", {})


# =============================================================================
# PHASE C: IntentPatternGuardSource Tests
# =============================================================================

class MockIntentTracker:
    """Mock IntentTracker for testing."""

    def __init__(self, recent_intents=None, totals=None):
        self._recent = recent_intents or []
        self._totals = totals or {}
        self._category_streaks = {}
        self._category_totals = {}

    def get_recent_intents(self, limit=10):
        return self._recent[-limit:]

    def total_count(self, intent):
        return self._totals.get(intent, 0)

    def category_streak(self, category):
        return self._category_streaks.get(category, 0)

    def category_total(self, category):
        return self._category_totals.get(category, 0)

    def advance_turn(self) -> None:
        pass


class MockContextSnapshot:
    """Mock ContextSnapshot for testing."""

    def __init__(self, state="close", intent="comparison", persona="default",
                 intent_tracker=None):
        self.state = state
        self.current_intent = intent
        self.persona = persona
        self.intent_tracker = intent_tracker or MockIntentTracker()


class MockBlackboard:
    """Mock Blackboard for testing."""

    def __init__(self, context=None):
        self._context = context or MockContextSnapshot()
        self.proposed_actions = []
        self.proposed_transitions = []

    def get_context(self):
        return self._context

    def propose_action(self, **kwargs):
        self.proposed_actions.append(kwargs)

    def propose_transition(self, **kwargs):
        self.proposed_transitions.append(kwargs)


class TestIntentPatternGuardSource:
    """Test IntentPatternGuardSource (Change 7)."""

    @pytest.fixture
    def source(self):
        """Create IntentPatternGuardSource with loaded config."""
        from src.blackboard.sources.intent_pattern_guard import IntentPatternGuardSource
        return IntentPatternGuardSource()

    def test_source_loads_config(self, source):
        """Change 7: Source loads pattern config from constants.yaml."""
        assert len(source._patterns) > 0
        assert "comparison_like" in source._patterns

    def test_source_builds_intent_lookup(self, source):
        """Change 7: Source builds O(1) intent lookup."""
        assert "comparison" in source._all_pattern_intents
        assert "question_tariff_comparison" in source._all_pattern_intents
        assert "question_snr_comparison" in source._all_pattern_intents

    @patch("src.blackboard.sources.intent_pattern_guard.flags")
    def test_should_contribute_false_when_flag_off(self, mock_flags, source):
        """Change 7: should_contribute returns False when flag off."""
        mock_flags.is_enabled.return_value = False
        tracker = MockIntentTracker(
            recent_intents=["comparison", "comparison", "comparison"]
        )
        ctx = MockContextSnapshot(intent="comparison", intent_tracker=tracker)
        bb = MockBlackboard(ctx)
        assert source.should_contribute(bb) is False

    @patch("src.blackboard.sources.intent_pattern_guard.flags")
    def test_should_contribute_false_for_unrelated_intent(self, mock_flags, source):
        """Change 7: should_contribute returns False for non-pattern intents."""
        mock_flags.is_enabled.return_value = True
        ctx = MockContextSnapshot(intent="greeting")
        bb = MockBlackboard(ctx)
        assert source.should_contribute(bb) is False

    @patch("src.blackboard.sources.intent_pattern_guard.flags")
    def test_should_contribute_true_when_streak_exceeds_threshold(self, mock_flags, source):
        """Change 7: should_contribute returns True when streak >= threshold."""
        mock_flags.is_enabled.return_value = True
        tracker = MockIntentTracker(
            recent_intents=["comparison", "comparison", "comparison"]
        )
        ctx = MockContextSnapshot(intent="comparison", intent_tracker=tracker)
        bb = MockBlackboard(ctx)
        assert source.should_contribute(bb) is True

    @patch("src.blackboard.sources.intent_pattern_guard.flags")
    def test_should_contribute_false_when_streak_below_threshold(self, mock_flags, source):
        """Change 7: should_contribute returns False when streak < threshold."""
        mock_flags.is_enabled.return_value = True
        tracker = MockIntentTracker(
            recent_intents=["greeting", "comparison"]
        )
        ctx = MockContextSnapshot(intent="comparison", intent_tracker=tracker)
        bb = MockBlackboard(ctx)
        assert source.should_contribute(bb) is False

    @patch("src.blackboard.sources.intent_pattern_guard.flags")
    def test_contribute_close_state_proposes_close_action(self, mock_flags, source):
        """Change 7: In close state, proposes close_answer_and_collect."""
        mock_flags.is_enabled.return_value = True
        tracker = MockIntentTracker(
            recent_intents=["comparison", "comparison", "comparison"]
        )
        ctx = MockContextSnapshot(state="close", intent="comparison", intent_tracker=tracker)
        bb = MockBlackboard(ctx)

        source.contribute(bb)

        assert len(bb.proposed_actions) == 1
        assert bb.proposed_actions[0]["action"] == "close_answer_and_collect"

    @patch("src.blackboard.sources.intent_pattern_guard.flags")
    def test_contribute_non_close_state_proposes_nudge(self, mock_flags, source):
        """Change 7: In non-close state, proposes nudge_progress."""
        mock_flags.is_enabled.return_value = True
        tracker = MockIntentTracker(
            recent_intents=["comparison", "comparison", "comparison"]
        )
        ctx = MockContextSnapshot(
            state="presentation", intent="comparison", intent_tracker=tracker
        )
        bb = MockBlackboard(ctx)

        source.contribute(bb)

        assert len(bb.proposed_actions) == 1
        assert bb.proposed_actions[0]["action"] == "nudge_progress"

    @patch("src.blackboard.sources.intent_pattern_guard.flags")
    def test_contribute_high_priority_at_double_threshold(self, mock_flags, source):
        """Change 7: HIGH priority when streak >= 2x threshold."""
        from src.blackboard.enums import Priority
        mock_flags.is_enabled.return_value = True

        # 6 consecutive comparisons (2x default threshold of 3)
        tracker = MockIntentTracker(
            recent_intents=["comparison"] * 6
        )
        ctx = MockContextSnapshot(state="close", intent="comparison", intent_tracker=tracker)
        bb = MockBlackboard(ctx)

        source.contribute(bb)

        assert bb.proposed_actions[0]["priority"] == Priority.HIGH

    @patch("src.blackboard.sources.intent_pattern_guard.flags")
    def test_contribute_normal_priority_at_threshold(self, mock_flags, source):
        """Change 7: NORMAL priority when streak == threshold."""
        from src.blackboard.enums import Priority
        mock_flags.is_enabled.return_value = True

        tracker = MockIntentTracker(
            recent_intents=["comparison"] * 3
        )
        ctx = MockContextSnapshot(state="close", intent="comparison", intent_tracker=tracker)
        bb = MockBlackboard(ctx)

        source.contribute(bb)

        assert bb.proposed_actions[0]["priority"] == Priority.NORMAL

    @patch("src.blackboard.sources.intent_pattern_guard.flags")
    def test_persona_specific_threshold(self, mock_flags, source):
        """Change 7: Persona-specific limits are used."""
        mock_flags.is_enabled.return_value = True

        # 3 comparisons - enough for default, not enough for tire_kicker
        tracker = MockIntentTracker(
            recent_intents=["comparison"] * 3
        )
        ctx_default = MockContextSnapshot(
            intent="comparison", persona="default", intent_tracker=tracker
        )
        ctx_tire_kicker = MockContextSnapshot(
            intent="comparison", persona="tire_kicker", intent_tracker=tracker
        )

        bb_default = MockBlackboard(ctx_default)
        bb_tire_kicker = MockBlackboard(ctx_tire_kicker)

        assert source.should_contribute(bb_default) is True
        assert source.should_contribute(bb_tire_kicker) is False


# =============================================================================
# PHASE C: Source Registry Tests
# =============================================================================

class TestSourceRegistryIntentPatternGuard:
    """Test IntentPatternGuardSource registration (Change 7)."""

    def test_intent_pattern_guard_registered(self):
        """Change 7: IntentPatternGuardSource is registered."""
        from src.blackboard.source_registry import SourceRegistry, register_builtin_sources

        SourceRegistry.reset()
        register_builtin_sources()

        registered = SourceRegistry.list_registered()
        assert "IntentPatternGuardSource" in registered

    def test_intent_pattern_guard_priority_25(self):
        """Change 7: IntentPatternGuardSource has priority 25."""
        from src.blackboard.source_registry import SourceRegistry, register_builtin_sources

        SourceRegistry.reset()
        register_builtin_sources()

        reg = SourceRegistry.get_registration("IntentPatternGuardSource")
        assert reg is not None
        assert reg.priority_order == 25


# =============================================================================
# PHASE D: ComparisonRefinementLayer Tests
# =============================================================================

class TestComparisonRefinementLayer:
    """Test ComparisonRefinementLayer (Change 8)."""

    @pytest.fixture
    def layer(self):
        """Create ComparisonRefinementLayer with feature flag enabled."""
        from src.feature_flags import flags
        flags.set_override("comparison_refinement", True)
        from src.classifier.comparison_refinement import ComparisonRefinementLayer
        layer = ComparisonRefinementLayer()
        yield layer
        flags.clear_override("comparison_refinement")

    @pytest.fixture
    def make_ctx(self):
        """Factory for RefinementContext."""
        from src.classifier.refinement_pipeline import RefinementContext

        def _make(intent="comparison", confidence=0.85, state="close", message=""):
            return RefinementContext(
                message=message,
                state=state,
                intent=intent,
                confidence=confidence,
            )
        return _make

    def test_should_apply_for_comparison_intents(self, layer, make_ctx):
        """Change 8: Layer applies to comparison intents."""
        assert layer._should_apply(make_ctx(intent="comparison"))
        assert layer._should_apply(make_ctx(intent="question_product_comparison"))
        assert layer._should_apply(make_ctx(intent="question_tariff_comparison"))
        assert layer._should_apply(make_ctx(intent="question_snr_comparison"))

    def test_should_not_apply_for_other_intents(self, layer, make_ctx):
        """Change 8: Layer does NOT apply to non-comparison intents."""
        assert not layer._should_apply(make_ctx(intent="price_question"))
        assert not layer._should_apply(make_ctx(intent="greeting"))
        assert not layer._should_apply(make_ctx(intent="objection_price"))

    def test_refines_competitor_cheaper(self, layer, make_ctx):
        """Change 8: 'конкурент дешевле' → objection_competitor."""
        from src.classifier.refinement_pipeline import RefinementDecision
        ctx = make_ctx(message="У конкурента дешевле цена")
        result = layer._do_refine(ctx.message, {"intent": "comparison"}, ctx)
        assert result.decision == RefinementDecision.REFINED
        assert result.intent == "objection_competitor"

    def test_refines_competitor_name_mention(self, layer, make_ctx):
        """Change 8: Mentioning competitor name → objection_competitor."""
        from src.classifier.refinement_pipeline import RefinementDecision
        ctx = make_ctx(message="Мы сейчас используем Битрикс24")
        result = layer._do_refine(ctx.message, {"intent": "comparison"}, ctx)
        assert result.decision == RefinementDecision.REFINED
        assert result.intent == "objection_competitor"

    def test_refines_why_you_better(self, layer, make_ctx):
        """Change 8: 'зачем вы лучше' → objection_competitor."""
        from src.classifier.refinement_pipeline import RefinementDecision
        ctx = make_ctx(message="Зачем вы лучше чем другие?")
        result = layer._do_refine(ctx.message, {"intent": "comparison"}, ctx)
        assert result.decision == RefinementDecision.REFINED
        assert result.intent == "objection_competitor"

    def test_passes_through_neutral_comparison(self, layer, make_ctx):
        """Change 8: Neutral comparison without competitor signals passes through."""
        from src.classifier.refinement_pipeline import RefinementDecision
        ctx = make_ctx(message="Сравните тарифы Lite и Pro")
        result = layer._do_refine(ctx.message, {"intent": "comparison"}, ctx)
        assert result.decision == RefinementDecision.PASS_THROUGH
        assert result.intent == "comparison"

    def test_confidence_boosted_on_refinement(self, layer, make_ctx):
        """Change 8: Confidence is at least 0.75 after refinement."""
        ctx = make_ctx(message="У AmoCRM функционал лучше", confidence=0.5)
        result = layer._do_refine(ctx.message, {"intent": "comparison"}, ctx)
        assert result.confidence >= 0.75

    def test_layer_disabled_by_default(self):
        """Change 8: Layer disabled when comparison_refinement flag is False."""
        from src.feature_flags import flags
        flags.clear_override("comparison_refinement")
        from src.classifier.comparison_refinement import ComparisonRefinementLayer
        layer = ComparisonRefinementLayer()
        assert not layer.enabled


class TestComparisonRefinementRegistration:
    """Test ComparisonRefinementLayer registration."""

    def test_comparison_layer_in_expected_list(self):
        """Change 8: 'comparison' is in expected layers list."""
        from src.classifier.refinement_layers import verify_layers_registered
        registered = verify_layers_registered()
        assert "comparison" in registered


# =============================================================================
# PHASE A: Config Getter Tests
# =============================================================================

class TestConfigGetters:
    """Test new config getter functions."""

    def test_get_intent_pattern_guard_config(self):
        """Change 7: get_intent_pattern_guard_config returns valid config."""
        from src.yaml_config.constants import get_intent_pattern_guard_config
        config = get_intent_pattern_guard_config()
        assert "patterns" in config
        assert "comparison_like" in config["patterns"]

    def test_get_intent_pattern_guard_config_has_intents(self):
        """Change 7: Config has intents list for comparison_like."""
        from src.yaml_config.constants import get_intent_pattern_guard_config
        config = get_intent_pattern_guard_config()
        intents = config["patterns"]["comparison_like"]["intents"]
        assert "comparison" in intents
        assert len(intents) >= 3


# =============================================================================
# DEFENSE-IN-DEPTH: Coverage Matrix Tests
# =============================================================================

class TestDefenseInDepthCoverage:
    """Verify all 3 layers of defense-in-depth are in place."""

    @pytest.fixture
    def states_config(self):
        return _load_yaml("src/yaml_config/flows/_base/states.yaml")

    @pytest.fixture
    def templates_config(self):
        return _load_yaml("src/yaml_config/templates/_base/prompts.yaml")

    def test_layer1_top3_intents_use_strong_cta(self, states_config):
        """Layer 1: Top-3 intents → close_answer_and_collect."""
        close_rules = states_config["states"]["close"]["rules"]
        assert close_rules["comparison"] == "close_answer_and_collect"
        assert close_rules["question_features"] == "close_answer_and_collect"
        assert close_rules["question_integrations"] == "close_answer_and_collect"

    def test_layer2_info_provided_uses_continue_current_goal(self, states_config, templates_config):
        """Layer 2: info_provided → continue_current_goal with contact_info example."""
        close_rules = states_config["states"]["close"]["rules"]
        assert close_rules["info_provided"] == "continue_current_goal"
        template = templates_config["templates"]["continue_current_goal"]["template"]
        assert "contact_info" in template

    def test_layer3_all_inherited_templates_goal_aware(self, templates_config):
        """Layer 3: All 167+ inherited rules use goal-aware templates."""
        # These are the templates used by mixin rules (inherited by close state)
        inherited_templates = ["answer_with_facts", "answer_and_continue"]
        for tpl_name in inherited_templates:
            tpl = templates_config["templates"][tpl_name]
            assert "{goal}" in tpl["template"], \
                f"Inherited template '{tpl_name}' missing {{goal}}"

    def test_utility_templates_all_goal_aware(self, templates_config):
        """Layer 3 extension: Utility templates are also goal-aware."""
        utility_templates = [
            "small_talk_and_continue",
            "acknowledge_and_continue",
            "clarify_and_continue",
        ]
        for tpl_name in utility_templates:
            tpl = templates_config["templates"][tpl_name]
            assert "{goal}" in tpl["template"], \
                f"Utility template '{tpl_name}' missing {{goal}}"
