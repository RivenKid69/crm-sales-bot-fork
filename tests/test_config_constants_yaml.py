"""
Comprehensive tests for constants.yaml configuration parameters.

Tests 100% coverage of all parameters in yaml_config/constants.yaml:
- SPIN configuration
- Limits
- Intent categories
- Dialogue policy settings
- Lead scoring
- Conversation guard
- Frustration tracker
- Circular flow
- Context window
- Fallback templates
- LLM fallback
- CTA settings
"""

import pytest
from pathlib import Path
import yaml

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# Path to constants.yaml
CONSTANTS_FILE = Path(__file__).parent.parent / "src" / "yaml_config" / "constants.yaml"


@pytest.fixture(scope="module")
def constants():
    """Load constants.yaml fixture."""
    with open(CONSTANTS_FILE, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


class TestSpinConfiguration:
    """Tests for SPIN selling configuration section."""

    def test_spin_phases_exist(self, constants):
        """Test spin.phases list exists and has correct phases."""
        assert "spin" in constants
        assert "phases" in constants["spin"]
        phases = constants["spin"]["phases"]
        assert "situation" in phases
        assert "problem" in phases
        assert "implication" in phases
        assert "need_payoff" in phases

    def test_spin_phases_order(self, constants):
        """Test spin phases are in correct SPIN order."""
        phases = constants["spin"]["phases"]
        assert phases == ["situation", "problem", "implication", "need_payoff"]

    def test_spin_states_mapping(self, constants):
        """Test spin.states mapping exists."""
        assert "states" in constants["spin"]
        states = constants["spin"]["states"]
        assert states["situation"] == "spin_situation"
        assert states["problem"] == "spin_problem"
        assert states["implication"] == "spin_implication"
        assert states["need_payoff"] == "spin_need_payoff"

    def test_spin_progress_intents(self, constants):
        """Test spin.progress_intents mapping."""
        assert "progress_intents" in constants["spin"]
        progress = constants["spin"]["progress_intents"]
        assert progress["situation_provided"] == "situation"
        assert progress["problem_revealed"] == "problem"
        assert progress["implication_acknowledged"] == "implication"
        assert progress["need_expressed"] == "need_payoff"

    def test_spin_phase_classification_situation(self, constants):
        """Test phase classification for situation."""
        pc = constants["spin"]["phase_classification"]
        assert "situation" in pc
        assert "data_fields" in pc["situation"]
        assert "company_size" in pc["situation"]["data_fields"]
        assert "current_tools" in pc["situation"]["data_fields"]
        assert "business_type" in pc["situation"]["data_fields"]
        assert pc["situation"]["intent"] == "situation_provided"
        assert pc["situation"]["confidence"] == 0.9

    def test_spin_phase_classification_problem(self, constants):
        """Test phase classification for problem."""
        pc = constants["spin"]["phase_classification"]
        assert "problem" in pc
        assert "pain_point" in pc["problem"]["data_fields"]
        assert pc["problem"]["intent"] == "problem_revealed"
        assert pc["problem"]["confidence"] == 0.9

    def test_spin_phase_classification_implication(self, constants):
        """Test phase classification for implication."""
        pc = constants["spin"]["phase_classification"]
        assert "implication" in pc
        assert "pain_impact" in pc["implication"]["data_fields"]
        assert "financial_impact" in pc["implication"]["data_fields"]
        assert pc["implication"]["intent"] == "implication_acknowledged"
        assert pc["implication"]["confidence"] == 0.9

    def test_spin_phase_classification_need_payoff(self, constants):
        """Test phase classification for need_payoff."""
        pc = constants["spin"]["phase_classification"]
        assert "need_payoff" in pc
        assert "desired_outcome" in pc["need_payoff"]["data_fields"]
        assert "value_acknowledged" in pc["need_payoff"]["data_fields"]
        assert pc["need_payoff"]["intent"] == "need_expressed"
        assert pc["need_payoff"]["confidence"] == 0.9

    def test_spin_short_answer_classification(self, constants):
        """Test short_answer_classification section."""
        sac = constants["spin"]["short_answer_classification"]

        # Situation
        assert sac["situation"]["positive_intent"] == "situation_provided"
        assert sac["situation"]["positive_confidence"] == 0.7

        # Problem
        assert sac["problem"]["positive_intent"] == "problem_revealed"
        assert sac["problem"]["positive_confidence"] == 0.75
        assert sac["problem"]["negative_intent"] == "no_problem"
        assert sac["problem"]["negative_confidence"] == 0.7

        # Implication
        assert sac["implication"]["positive_intent"] == "implication_acknowledged"
        assert sac["implication"]["positive_confidence"] == 0.8

        # Need payoff
        assert sac["need_payoff"]["positive_intent"] == "need_expressed"
        assert sac["need_payoff"]["positive_confidence"] == 0.85
        assert sac["need_payoff"]["negative_intent"] == "no_need"
        assert sac["need_payoff"]["negative_confidence"] == 0.7


class TestLimitsConfiguration:
    """Tests for limits configuration section."""

    def test_limits_section_exists(self, constants):
        """Test limits section exists."""
        assert "limits" in constants

    def test_max_consecutive_objections(self, constants):
        """Test limits.max_consecutive_objections parameter."""
        assert "max_consecutive_objections" in constants["limits"]
        assert constants["limits"]["max_consecutive_objections"] == 3
        assert isinstance(constants["limits"]["max_consecutive_objections"], int)

    def test_max_total_objections(self, constants):
        """Test limits.max_total_objections parameter."""
        assert "max_total_objections" in constants["limits"]
        assert constants["limits"]["max_total_objections"] == 5
        assert isinstance(constants["limits"]["max_total_objections"], int)

    def test_max_gobacks(self, constants):
        """Test limits.max_gobacks parameter."""
        assert "max_gobacks" in constants["limits"]
        assert constants["limits"]["max_gobacks"] == 2
        assert isinstance(constants["limits"]["max_gobacks"], int)

    def test_limits_values_positive(self, constants):
        """Test all limits are positive numbers."""
        limits = constants["limits"]
        for key, value in limits.items():
            assert value > 0, f"Limit {key} should be positive, got {value}"


class TestIntentsConfiguration:
    """Tests for intents configuration section."""

    def test_intents_section_exists(self, constants):
        """Test intents section exists."""
        assert "intents" in constants

    def test_go_back_intents(self, constants):
        """Test intents.go_back list."""
        assert "go_back" in constants["intents"]
        go_back = constants["intents"]["go_back"]
        assert "go_back" in go_back
        assert "correct_info" in go_back

    def test_categories_objection(self, constants):
        """Test intents.categories.objection list."""
        categories = constants["intents"]["categories"]
        assert "objection" in categories
        objections = categories["objection"]
        assert "objection_price" in objections
        assert "objection_competitor" in objections
        assert "objection_no_time" in objections
        assert "objection_think" in objections

    def test_categories_positive(self, constants):
        """Test intents.categories.positive list."""
        categories = constants["intents"]["categories"]
        assert "positive" in categories
        positive = categories["positive"]
        assert "agreement" in positive
        assert "demo_request" in positive
        assert "callback_request" in positive
        assert "contact_provided" in positive
        assert "consultation_request" in positive
        assert "situation_provided" in positive
        assert "problem_revealed" in positive
        assert "implication_acknowledged" in positive
        assert "need_expressed" in positive
        assert "info_provided" in positive
        assert "question_features" in positive
        assert "question_integrations" in positive
        assert "comparison" in positive
        assert "greeting" in positive
        assert "gratitude" in positive

    def test_categories_question(self, constants):
        """Test intents.categories.question list."""
        categories = constants["intents"]["categories"]
        assert "question" in categories
        question = categories["question"]
        assert "price_question" in question
        assert "pricing_details" in question
        assert "question_features" in question
        assert "question_integrations" in question
        assert "question_technical" in question
        assert "comparison" in question

    def test_categories_spin_progress(self, constants):
        """Test intents.categories.spin_progress list."""
        categories = constants["intents"]["categories"]
        assert "spin_progress" in categories
        spin_progress = categories["spin_progress"]
        assert "situation_provided" in spin_progress
        assert "problem_revealed" in spin_progress
        assert "implication_acknowledged" in spin_progress
        assert "need_expressed" in spin_progress

    def test_categories_negative(self, constants):
        """Test intents.categories.negative - now a composed category.

        negative is now defined via composed_categories in YAML and built
        programmatically in constants.py by merging objection + exit categories.
        This eliminates duplication and ensures automatic synchronization.
        """
        # Verify composed_categories definition exists
        composed = constants["intents"].get("composed_categories", {})
        assert "negative" in composed, "negative should be in composed_categories"
        assert "includes" in composed["negative"], "negative should have includes"
        assert "objection" in composed["negative"]["includes"]
        assert "exit" in composed["negative"]["includes"]

        # Verify exit category exists (base category for rejection/farewell)
        categories = constants["intents"]["categories"]
        assert "exit" in categories, "exit category should exist"
        exit_intents = categories["exit"]
        assert "rejection" in exit_intents
        assert "farewell" in exit_intents

        # Verify the resolved INTENT_CATEGORIES has negative properly composed
        from src.yaml_config.constants import INTENT_CATEGORIES
        assert "negative" in INTENT_CATEGORIES, "negative should be in INTENT_CATEGORIES"
        negative = INTENT_CATEGORIES["negative"]
        assert "rejection" in negative, "negative should include rejection (from exit)"
        assert "farewell" in negative, "negative should include farewell (from exit)"
        assert "objection_price" in negative, "negative should include objection_price"
        assert "objection_competitor" in negative, "negative should include objection_competitor"
        assert "objection_no_time" in negative, "negative should include objection_no_time"
        assert "objection_think" in negative, "negative should include objection_think"


class TestComposedCategories:
    """Tests for composed categories feature - automatic category composition."""

    def test_composed_categories_section_exists(self, constants):
        """Test that composed_categories section exists in intents."""
        assert "composed_categories" in constants["intents"]

    def test_negative_is_composed(self, constants):
        """Test that negative is properly defined as composed category."""
        composed = constants["intents"]["composed_categories"]
        assert "negative" in composed
        assert "includes" in composed["negative"]
        includes = composed["negative"]["includes"]
        assert "objection" in includes
        assert "exit" in includes

    def test_blocking_is_composed(self, constants):
        """Test that blocking is properly defined as composed category."""
        composed = constants["intents"]["composed_categories"]
        assert "blocking" in composed
        includes = composed["blocking"]["includes"]
        assert "objection" in includes
        assert "exit" in includes
        assert "technical_problems" in includes

    def test_all_questions_is_composed(self, constants):
        """Test that all_questions is properly defined as composed category."""
        composed = constants["intents"]["composed_categories"]
        assert "all_questions" in composed
        includes = composed["all_questions"]["includes"]
        assert "question" in includes
        assert "equipment_questions" in includes
        assert "tariff_questions" in includes

    def test_composed_categories_have_descriptions(self, constants):
        """Test that all composed categories have descriptions."""
        composed = constants["intents"]["composed_categories"]
        for name, spec in composed.items():
            assert "description" in spec, f"Composed category '{name}' missing description"

    def test_exit_category_exists(self, constants):
        """Test that exit category exists as base category."""
        categories = constants["intents"]["categories"]
        assert "exit" in categories
        exit_intents = categories["exit"]
        assert "rejection" in exit_intents
        assert "farewell" in exit_intents
        assert len(exit_intents) == 2

    def test_rejection_not_in_objection(self, constants):
        """Test that rejection is NOT in objection category (semantic fix)."""
        categories = constants["intents"]["categories"]
        objections = categories["objection"]
        assert "rejection" not in objections, \
            "rejection should NOT be in objection - it's a final refusal, not a handleable objection"

    def test_composed_category_resolution(self):
        """Test that INTENT_CATEGORIES contains resolved composed categories."""
        from src.yaml_config.constants import INTENT_CATEGORIES

        # negative should exist and be properly composed
        assert "negative" in INTENT_CATEGORIES
        negative = INTENT_CATEGORIES["negative"]

        # Should include objection intents
        assert "objection_price" in negative
        assert "objection_no_time" in negative

        # Should include exit intents
        assert "rejection" in negative
        assert "farewell" in negative

    def test_no_duplication_in_composed(self):
        """Test that composed categories have no duplicate intents."""
        from src.yaml_config.constants import INTENT_CATEGORIES

        for name, intents in INTENT_CATEGORIES.items():
            unique = set(intents)
            assert len(intents) == len(unique), \
                f"Category '{name}' has duplicates: {len(intents)} vs {len(unique)} unique"

    def test_composed_categories_are_supersets(self):
        """Test that composed categories are proper supersets of their includes."""
        from src.yaml_config.constants import INTENT_CATEGORIES

        # negative should be superset of objection and exit
        negative_set = set(INTENT_CATEGORIES["negative"])
        objection_set = set(INTENT_CATEGORIES["objection"])
        exit_set = set(INTENT_CATEGORIES["exit"])

        assert objection_set.issubset(negative_set), "objection should be subset of negative"
        assert exit_set.issubset(negative_set), "exit should be subset of negative"

        # blocking should be superset of objection, exit, and technical_problems
        blocking_set = set(INTENT_CATEGORIES["blocking"])
        technical_set = set(INTENT_CATEGORIES["technical_problems"])

        assert objection_set.issubset(blocking_set), "objection should be subset of blocking"
        assert exit_set.issubset(blocking_set), "exit should be subset of blocking"
        assert technical_set.issubset(blocking_set), "technical_problems should be subset of blocking"


class TestDialoguePolicyConfiguration:
    """Tests for dialogue policy configuration section."""

    def test_policy_section_exists(self, constants):
        """Test policy section exists."""
        assert "policy" in constants

    def test_overlay_allowed_states(self, constants):
        """Test policy.overlay_allowed_states list."""
        allowed = constants["policy"]["overlay_allowed_states"]
        assert "spin_situation" in allowed
        assert "spin_problem" in allowed
        assert "spin_implication" in allowed
        assert "spin_need_payoff" in allowed
        assert "presentation" in allowed
        assert "handle_objection" in allowed

    def test_protected_states(self, constants):
        """Test policy.protected_states list."""
        protected = constants["policy"]["protected_states"]
        assert "greeting" in protected
        assert "close" in protected
        assert "success" in protected
        assert "soft_close" in protected

    def test_aggressive_actions(self, constants):
        """Test policy.aggressive_actions list."""
        aggressive = constants["policy"]["aggressive_actions"]
        assert "transition_to_presentation" in aggressive
        assert "transition_to_close" in aggressive
        assert "ask_for_demo" in aggressive
        assert "ask_for_contact" in aggressive

    def test_repair_actions(self, constants):
        """Test policy.repair_actions mapping."""
        repair = constants["policy"]["repair_actions"]
        assert repair["stuck"] == "clarify_one_question"
        assert repair["oscillation"] == "summarize_and_clarify"
        assert repair["repeated_question"] == "answer_with_summary"

    def test_objection_actions(self, constants):
        """Test policy.objection_actions mapping."""
        objection = constants["policy"]["objection_actions"]
        assert objection["reframe"] == "reframe_value"
        assert objection["escalate"] == "handle_repeated_objection"
        assert objection["empathize"] == "empathize_and_redirect"


class TestLeadScoringConfiguration:
    """Tests for lead scoring configuration section."""

    def test_lead_scoring_section_exists(self, constants):
        """Test lead_scoring section exists."""
        assert "lead_scoring" in constants

    def test_positive_weights_demo_request(self, constants):
        """Test lead_scoring.positive_weights.demo_request."""
        weights = constants["lead_scoring"]["positive_weights"]
        assert weights["demo_request"] == 30

    def test_positive_weights_price_with_size(self, constants):
        """Test lead_scoring.positive_weights.price_with_size."""
        weights = constants["lead_scoring"]["positive_weights"]
        assert weights["price_with_size"] == 25

    def test_positive_weights_callback_request(self, constants):
        """Test lead_scoring.positive_weights.callback_request."""
        weights = constants["lead_scoring"]["positive_weights"]
        assert weights["callback_request"] == 25

    def test_positive_weights_consultation_request(self, constants):
        """Test lead_scoring.positive_weights.consultation_request."""
        weights = constants["lead_scoring"]["positive_weights"]
        assert weights["consultation_request"] == 20

    def test_positive_weights_contact_provided(self, constants):
        """Test lead_scoring.positive_weights.contact_provided."""
        weights = constants["lead_scoring"]["positive_weights"]
        assert weights["contact_provided"] == 35

    def test_positive_weights_explicit_problem(self, constants):
        """Test lead_scoring.positive_weights.explicit_problem."""
        weights = constants["lead_scoring"]["positive_weights"]
        assert weights["explicit_problem"] == 15

    def test_positive_weights_competitor_comparison(self, constants):
        """Test lead_scoring.positive_weights.competitor_comparison."""
        weights = constants["lead_scoring"]["positive_weights"]
        assert weights["competitor_comparison"] == 12

    def test_positive_weights_budget_mentioned(self, constants):
        """Test lead_scoring.positive_weights.budget_mentioned."""
        weights = constants["lead_scoring"]["positive_weights"]
        assert weights["budget_mentioned"] == 10

    def test_positive_weights_timeline_mentioned(self, constants):
        """Test lead_scoring.positive_weights.timeline_mentioned."""
        weights = constants["lead_scoring"]["positive_weights"]
        assert weights["timeline_mentioned"] == 10

    def test_positive_weights_multiple_questions(self, constants):
        """Test lead_scoring.positive_weights.multiple_questions."""
        weights = constants["lead_scoring"]["positive_weights"]
        assert weights["multiple_questions"] == 8

    def test_positive_weights_features_question(self, constants):
        """Test lead_scoring.positive_weights.features_question."""
        weights = constants["lead_scoring"]["positive_weights"]
        assert weights["features_question"] == 5

    def test_positive_weights_integrations_question(self, constants):
        """Test lead_scoring.positive_weights.integrations_question."""
        weights = constants["lead_scoring"]["positive_weights"]
        assert weights["integrations_question"] == 5

    def test_positive_weights_general_interest(self, constants):
        """Test lead_scoring.positive_weights.general_interest."""
        weights = constants["lead_scoring"]["positive_weights"]
        assert weights["general_interest"] == 3

    def test_positive_weights_price_question(self, constants):
        """Test lead_scoring.positive_weights.price_question."""
        weights = constants["lead_scoring"]["positive_weights"]
        assert weights["price_question"] == 5

    def test_negative_weights_objection_price(self, constants):
        """Test lead_scoring.negative_weights.objection_price."""
        weights = constants["lead_scoring"]["negative_weights"]
        assert weights["objection_price"] == -15

    def test_negative_weights_objection_competitor(self, constants):
        """Test lead_scoring.negative_weights.objection_competitor."""
        weights = constants["lead_scoring"]["negative_weights"]
        assert weights["objection_competitor"] == -10

    def test_negative_weights_objection_no_time(self, constants):
        """Test lead_scoring.negative_weights.objection_no_time."""
        weights = constants["lead_scoring"]["negative_weights"]
        assert weights["objection_no_time"] == -20

    def test_negative_weights_objection_think(self, constants):
        """Test lead_scoring.negative_weights.objection_think."""
        weights = constants["lead_scoring"]["negative_weights"]
        assert weights["objection_think"] == -10

    def test_negative_weights_objection_no_need(self, constants):
        """Test lead_scoring.negative_weights.objection_no_need."""
        weights = constants["lead_scoring"]["negative_weights"]
        assert weights["objection_no_need"] == -25

    def test_negative_weights_unclear_repeated(self, constants):
        """Test lead_scoring.negative_weights.unclear_repeated."""
        weights = constants["lead_scoring"]["negative_weights"]
        assert weights["unclear_repeated"] == -5

    def test_negative_weights_rejection_soft(self, constants):
        """Test lead_scoring.negative_weights.rejection_soft."""
        weights = constants["lead_scoring"]["negative_weights"]
        assert weights["rejection_soft"] == -25

    def test_negative_weights_frustration(self, constants):
        """Test lead_scoring.negative_weights.frustration."""
        weights = constants["lead_scoring"]["negative_weights"]
        assert weights["frustration"] == -15

    def test_thresholds_cold(self, constants):
        """Test lead_scoring.thresholds.cold range."""
        thresholds = constants["lead_scoring"]["thresholds"]
        assert thresholds["cold"] == [0, 29]

    def test_thresholds_warm(self, constants):
        """Test lead_scoring.thresholds.warm range."""
        thresholds = constants["lead_scoring"]["thresholds"]
        assert thresholds["warm"] == [30, 49]

    def test_thresholds_hot(self, constants):
        """Test lead_scoring.thresholds.hot range."""
        thresholds = constants["lead_scoring"]["thresholds"]
        assert thresholds["hot"] == [50, 69]

    def test_thresholds_very_hot(self, constants):
        """Test lead_scoring.thresholds.very_hot range."""
        thresholds = constants["lead_scoring"]["thresholds"]
        assert thresholds["very_hot"] == [70, 100]

    def test_skip_phases_cold(self, constants):
        """Test lead_scoring.skip_phases.cold (no skips)."""
        skip = constants["lead_scoring"]["skip_phases"]
        assert skip["cold"] == []

    def test_skip_phases_warm(self, constants):
        """Test lead_scoring.skip_phases.warm."""
        skip = constants["lead_scoring"]["skip_phases"]
        assert "spin_implication" in skip["warm"]
        assert "spin_need_payoff" in skip["warm"]

    def test_skip_phases_hot(self, constants):
        """Test lead_scoring.skip_phases.hot."""
        skip = constants["lead_scoring"]["skip_phases"]
        assert "spin_problem" in skip["hot"]
        assert "spin_implication" in skip["hot"]
        assert "spin_need_payoff" in skip["hot"]

    def test_skip_phases_very_hot(self, constants):
        """Test lead_scoring.skip_phases.very_hot."""
        skip = constants["lead_scoring"]["skip_phases"]
        assert "spin_situation" in skip["very_hot"]
        assert "spin_problem" in skip["very_hot"]
        assert "spin_implication" in skip["very_hot"]
        assert "spin_need_payoff" in skip["very_hot"]

    def test_paths(self, constants):
        """Test lead_scoring.paths mapping."""
        paths = constants["lead_scoring"]["paths"]
        assert paths["cold"] == "full_spin"
        assert paths["warm"] == "short_spin"
        assert paths["hot"] == "direct_present"
        assert paths["very_hot"] == "direct_close"


class TestConversationGuardConfiguration:
    """Tests for conversation guard configuration section."""

    def test_guard_section_exists(self, constants):
        """Test guard section exists."""
        assert "guard" in constants

    def test_max_turns(self, constants):
        """Test guard.max_turns parameter."""
        assert constants["guard"]["max_turns"] == 25

    def test_max_phase_attempts(self, constants):
        """Test guard.max_phase_attempts parameter."""
        assert constants["guard"]["max_phase_attempts"] == 3

    def test_max_same_state(self, constants):
        """Test guard.max_same_state parameter."""
        assert constants["guard"]["max_same_state"] == 4

    def test_max_same_message(self, constants):
        """Test guard.max_same_message parameter."""
        assert constants["guard"]["max_same_message"] == 2

    def test_timeout_seconds(self, constants):
        """Test guard.timeout_seconds parameter."""
        assert constants["guard"]["timeout_seconds"] == 1800  # 30 minutes

    def test_progress_check_interval(self, constants):
        """Test guard.progress_check_interval parameter."""
        assert constants["guard"]["progress_check_interval"] == 5

    def test_min_unique_states_for_progress(self, constants):
        """Test guard.min_unique_states_for_progress parameter."""
        assert constants["guard"]["min_unique_states_for_progress"] == 2

    def test_high_frustration_threshold(self, constants):
        """Test guard.high_frustration_threshold parameter."""
        assert constants["guard"]["high_frustration_threshold"] == 7

    def test_profiles_strict(self, constants):
        """Test guard.profiles.strict configuration."""
        strict = constants["guard"]["profiles"]["strict"]
        assert strict["max_turns"] == 15
        assert strict["max_phase_attempts"] == 2
        assert strict["max_same_state"] == 3
        assert strict["timeout_seconds"] == 900  # 15 minutes

    def test_profiles_relaxed(self, constants):
        """Test guard.profiles.relaxed configuration."""
        relaxed = constants["guard"]["profiles"]["relaxed"]
        assert relaxed["max_turns"] == 40
        assert relaxed["max_phase_attempts"] == 5
        assert relaxed["max_same_state"] == 6
        assert relaxed["timeout_seconds"] == 3600  # 1 hour


class TestFrustrationTrackerConfiguration:
    """Tests for frustration tracker configuration section."""

    def test_frustration_section_exists(self, constants):
        """Test frustration section exists."""
        assert "frustration" in constants

    def test_max_level(self, constants):
        """Test frustration.max_level parameter."""
        assert constants["frustration"]["max_level"] == 10

    def test_weights_frustrated(self, constants):
        """Test frustration.weights.frustrated."""
        assert constants["frustration"]["weights"]["frustrated"] == 3

    def test_weights_skeptical(self, constants):
        """Test frustration.weights.skeptical."""
        assert constants["frustration"]["weights"]["skeptical"] == 1

    def test_weights_rushed(self, constants):
        """Test frustration.weights.rushed."""
        assert constants["frustration"]["weights"]["rushed"] == 1

    def test_weights_confused(self, constants):
        """Test frustration.weights.confused."""
        assert constants["frustration"]["weights"]["confused"] == 1

    def test_decay_neutral(self, constants):
        """Test frustration.decay.neutral."""
        assert constants["frustration"]["decay"]["neutral"] == 1

    def test_decay_positive(self, constants):
        """Test frustration.decay.positive."""
        assert constants["frustration"]["decay"]["positive"] == 2

    def test_decay_interested(self, constants):
        """Test frustration.decay.interested."""
        assert constants["frustration"]["decay"]["interested"] == 2

    def test_thresholds_warning(self, constants):
        """Test frustration.thresholds.warning."""
        assert constants["frustration"]["thresholds"]["warning"] == 4

    def test_thresholds_high(self, constants):
        """Test frustration.thresholds.high."""
        assert constants["frustration"]["thresholds"]["high"] == 7

    def test_thresholds_critical(self, constants):
        """Test frustration.thresholds.critical."""
        assert constants["frustration"]["thresholds"]["critical"] == 9

    def test_threshold_consistency(self, constants):
        """Test that guard.high_frustration_threshold equals frustration.thresholds.high."""
        guard_threshold = constants["guard"]["high_frustration_threshold"]
        frustration_high = constants["frustration"]["thresholds"]["high"]
        assert guard_threshold == frustration_high, \
            f"Threshold mismatch: guard={guard_threshold}, frustration={frustration_high}"


class TestCircularFlowConfiguration:
    """Tests for circular flow configuration section."""

    def test_circular_flow_section_exists(self, constants):
        """Test circular_flow section exists."""
        assert "circular_flow" in constants

    def test_allowed_gobacks(self, constants):
        """Test circular_flow.allowed_gobacks mapping."""
        gobacks = constants["circular_flow"]["allowed_gobacks"]

        assert gobacks["spin_problem"] == "spin_situation"
        assert gobacks["spin_implication"] == "spin_problem"
        assert gobacks["spin_need_payoff"] == "spin_implication"
        assert gobacks["presentation"] == "spin_need_payoff"
        assert gobacks["close"] == "presentation"
        assert gobacks["handle_objection"] == "presentation"
        assert gobacks["soft_close"] == "greeting"


class TestContextWindowConfiguration:
    """Tests for context window configuration section."""

    def test_context_section_exists(self, constants):
        """Test context section exists."""
        assert "context" in constants

    def test_state_order(self, constants):
        """Test context.state_order mapping."""
        order = constants["context"]["state_order"]

        assert order["greeting"] == 0
        assert order["spin_situation"] == 1
        assert order["spin_problem"] == 2
        assert order["spin_implication"] == 3
        assert order["spin_need_payoff"] == 4
        assert order["presentation"] == 5
        assert order["handle_objection"] == 5  # Parallel with presentation
        assert order["close"] == 6
        assert order["success"] == 7
        assert order["soft_close"] == -1  # Negative progress

    def test_phase_order(self, constants):
        """Test context.phase_order mapping."""
        order = constants["context"]["phase_order"]

        assert order["greeting"] == 0
        assert order["situation"] == 1
        assert order["problem"] == 2
        assert order["implication"] == 3
        assert order["need_payoff"] == 4
        assert order["presentation"] == 5
        assert order["close"] == 6
        assert order["success"] == 7


class TestFallbackConfiguration:
    """Tests for fallback configuration section."""

    def test_fallback_section_exists(self, constants):
        """Test fallback section exists."""
        assert "fallback" in constants

    def test_rephrase_templates_greeting(self, constants):
        """Test fallback.rephrase_templates.greeting."""
        templates = constants["fallback"]["rephrase_templates"]["greeting"]
        assert len(templates) >= 1
        assert any("Добрый день" in t or "Здравствуйте" in t for t in templates)

    def test_rephrase_templates_spin_situation(self, constants):
        """Test fallback.rephrase_templates.spin_situation."""
        templates = constants["fallback"]["rephrase_templates"]["spin_situation"]
        assert len(templates) >= 3

    def test_rephrase_templates_spin_problem(self, constants):
        """Test fallback.rephrase_templates.spin_problem."""
        templates = constants["fallback"]["rephrase_templates"]["spin_problem"]
        assert len(templates) >= 3

    def test_rephrase_templates_spin_implication(self, constants):
        """Test fallback.rephrase_templates.spin_implication."""
        templates = constants["fallback"]["rephrase_templates"]["spin_implication"]
        assert len(templates) >= 3

    def test_rephrase_templates_spin_need_payoff(self, constants):
        """Test fallback.rephrase_templates.spin_need_payoff."""
        templates = constants["fallback"]["rephrase_templates"]["spin_need_payoff"]
        assert len(templates) >= 3

    def test_rephrase_templates_presentation(self, constants):
        """Test fallback.rephrase_templates.presentation."""
        templates = constants["fallback"]["rephrase_templates"]["presentation"]
        assert len(templates) >= 2

    def test_rephrase_templates_close(self, constants):
        """Test fallback.rephrase_templates.close."""
        templates = constants["fallback"]["rephrase_templates"]["close"]
        assert len(templates) >= 2

    def test_rephrase_templates_handle_objection(self, constants):
        """Test fallback.rephrase_templates.handle_objection."""
        templates = constants["fallback"]["rephrase_templates"]["handle_objection"]
        assert len(templates) >= 2

    def test_options_templates_spin_situation(self, constants):
        """Test fallback.options_templates.spin_situation."""
        opts = constants["fallback"]["options_templates"]["spin_situation"]
        assert "question" in opts
        assert "options" in opts
        assert len(opts["options"]) >= 3

    def test_options_templates_spin_problem(self, constants):
        """Test fallback.options_templates.spin_problem."""
        opts = constants["fallback"]["options_templates"]["spin_problem"]
        assert "question" in opts
        assert "options" in opts
        assert len(opts["options"]) >= 3

    def test_options_templates_spin_implication(self, constants):
        """Test fallback.options_templates.spin_implication."""
        opts = constants["fallback"]["options_templates"]["spin_implication"]
        assert "question" in opts
        assert "options" in opts
        assert len(opts["options"]) >= 3

    def test_options_templates_spin_need_payoff(self, constants):
        """Test fallback.options_templates.spin_need_payoff."""
        opts = constants["fallback"]["options_templates"]["spin_need_payoff"]
        assert "question" in opts
        assert "options" in opts
        assert len(opts["options"]) >= 3

    def test_options_templates_presentation(self, constants):
        """Test fallback.options_templates.presentation."""
        opts = constants["fallback"]["options_templates"]["presentation"]
        assert "question" in opts
        assert "options" in opts
        assert len(opts["options"]) >= 3

    def test_default_rephrase(self, constants):
        """Test fallback.default_rephrase."""
        assert "default_rephrase" in constants["fallback"]
        assert len(constants["fallback"]["default_rephrase"]) > 0

    def test_default_options(self, constants):
        """Test fallback.default_options."""
        default = constants["fallback"]["default_options"]
        assert "question" in default
        assert "options" in default
        assert len(default["options"]) >= 3


class TestLLMFallbackConfiguration:
    """Tests for LLM fallback configuration section."""

    def test_llm_section_exists(self, constants):
        """Test llm section exists."""
        assert "llm" in constants

    def test_fallback_responses_greeting(self, constants):
        """Test llm.fallback_responses.greeting."""
        responses = constants["llm"]["fallback_responses"]
        assert "greeting" in responses
        assert len(responses["greeting"]) > 0

    def test_fallback_responses_spin_situation(self, constants):
        """Test llm.fallback_responses.spin_situation."""
        responses = constants["llm"]["fallback_responses"]
        assert "spin_situation" in responses
        assert len(responses["spin_situation"]) > 0

    def test_fallback_responses_spin_problem(self, constants):
        """Test llm.fallback_responses.spin_problem."""
        responses = constants["llm"]["fallback_responses"]
        assert "spin_problem" in responses
        assert len(responses["spin_problem"]) > 0

    def test_fallback_responses_spin_implication(self, constants):
        """Test llm.fallback_responses.spin_implication."""
        responses = constants["llm"]["fallback_responses"]
        assert "spin_implication" in responses
        assert len(responses["spin_implication"]) > 0

    def test_fallback_responses_spin_need_payoff(self, constants):
        """Test llm.fallback_responses.spin_need_payoff."""
        responses = constants["llm"]["fallback_responses"]
        assert "spin_need_payoff" in responses
        assert len(responses["spin_need_payoff"]) > 0

    def test_fallback_responses_presentation(self, constants):
        """Test llm.fallback_responses.presentation."""
        responses = constants["llm"]["fallback_responses"]
        assert "presentation" in responses
        assert len(responses["presentation"]) > 0

    def test_fallback_responses_close(self, constants):
        """Test llm.fallback_responses.close."""
        responses = constants["llm"]["fallback_responses"]
        assert "close" in responses
        assert len(responses["close"]) > 0

    def test_fallback_responses_soft_close(self, constants):
        """Test llm.fallback_responses.soft_close."""
        responses = constants["llm"]["fallback_responses"]
        assert "soft_close" in responses
        assert len(responses["soft_close"]) > 0

    def test_fallback_responses_handle_objection(self, constants):
        """Test llm.fallback_responses.handle_objection."""
        responses = constants["llm"]["fallback_responses"]
        assert "handle_objection" in responses
        assert len(responses["handle_objection"]) > 0

    def test_default_fallback(self, constants):
        """Test llm.default_fallback."""
        assert "default_fallback" in constants["llm"]
        assert len(constants["llm"]["default_fallback"]) > 0


class TestCTAConfiguration:
    """Tests for CTA (Call-to-Action) configuration section."""

    def test_cta_section_exists(self, constants):
        """Test cta section exists."""
        assert "cta" in constants

    def test_early_states(self, constants):
        """Test cta.early_states list."""
        early = constants["cta"]["early_states"]
        assert "greeting" in early
        assert "spin_situation" in early
        assert "spin_problem" in early

    def test_templates_greeting_empty(self, constants):
        """Test cta.templates.greeting is empty (early state)."""
        templates = constants["cta"]["templates"]
        assert templates["greeting"] == []

    def test_templates_spin_situation_empty(self, constants):
        """Test cta.templates.spin_situation is empty (early state)."""
        templates = constants["cta"]["templates"]
        assert templates["spin_situation"] == []

    def test_templates_spin_problem_empty(self, constants):
        """Test cta.templates.spin_problem is empty (early state)."""
        templates = constants["cta"]["templates"]
        assert templates["spin_problem"] == []

    def test_templates_spin_implication(self, constants):
        """Test cta.templates.spin_implication has CTAs."""
        templates = constants["cta"]["templates"]
        assert len(templates["spin_implication"]) >= 1

    def test_templates_spin_need_payoff(self, constants):
        """Test cta.templates.spin_need_payoff has CTAs."""
        templates = constants["cta"]["templates"]
        assert len(templates["spin_need_payoff"]) >= 2

    def test_templates_presentation(self, constants):
        """Test cta.templates.presentation has CTAs."""
        templates = constants["cta"]["templates"]
        assert len(templates["presentation"]) >= 3

    def test_templates_handle_objection(self, constants):
        """Test cta.templates.handle_objection has CTAs."""
        templates = constants["cta"]["templates"]
        assert len(templates["handle_objection"]) >= 1

    def test_templates_close(self, constants):
        """Test cta.templates.close has CTAs."""
        templates = constants["cta"]["templates"]
        assert len(templates["close"]) >= 2

    def test_by_action_demo(self, constants):
        """Test cta.by_action.demo list."""
        by_action = constants["cta"]["by_action"]
        assert "demo" in by_action
        assert len(by_action["demo"]) >= 2

    def test_by_action_contact(self, constants):
        """Test cta.by_action.contact list."""
        by_action = constants["cta"]["by_action"]
        assert "contact" in by_action
        assert len(by_action["contact"]) >= 2

    def test_by_action_trial(self, constants):
        """Test cta.by_action.trial list."""
        by_action = constants["cta"]["by_action"]
        assert "trial" in by_action
        assert len(by_action["trial"]) >= 1


class TestConstantsConsistency:
    """Tests for internal consistency of constants."""

    def test_spin_phases_match_states(self, constants):
        """Test that all spin phases have corresponding states."""
        phases = constants["spin"]["phases"]
        states_mapping = constants["spin"]["states"]

        for phase in phases:
            assert phase in states_mapping, f"Phase {phase} missing in states mapping"

    def test_progress_intents_match_phases(self, constants):
        """Test that progress intents map to valid phases."""
        phases = constants["spin"]["phases"]
        progress_intents = constants["spin"]["progress_intents"]

        for intent, phase in progress_intents.items():
            assert phase in phases, f"Intent {intent} maps to invalid phase {phase}"

    def test_skip_phases_states_are_valid(self, constants):
        """Test that skip_phases references valid states."""
        spin_states = list(constants["spin"]["states"].values())
        skip_phases = constants["lead_scoring"]["skip_phases"]

        for temp, states in skip_phases.items():
            for state in states:
                assert state in spin_states, f"Invalid state {state} in skip_phases.{temp}"

    def test_allowed_gobacks_source_states_valid(self, constants):
        """Test that circular_flow.allowed_gobacks has valid source states."""
        gobacks = constants["circular_flow"]["allowed_gobacks"]
        state_order = constants["context"]["state_order"]

        for source in gobacks.keys():
            assert source in state_order, f"Invalid source state {source} in allowed_gobacks"

    def test_allowed_gobacks_target_states_valid(self, constants):
        """Test that circular_flow.allowed_gobacks has valid target states."""
        gobacks = constants["circular_flow"]["allowed_gobacks"]
        state_order = constants["context"]["state_order"]

        for source, target in gobacks.items():
            assert target in state_order, f"Invalid target state {target} from {source}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
