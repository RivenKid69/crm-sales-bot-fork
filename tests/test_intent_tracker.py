"""
Tests for IntentTracker - Phase 3.

This test suite provides 100% coverage for:
- IntentTracker class
- IntentRecord dataclass
- INTENT_CATEGORIES definitions
- Streak counting
- Category tracking
- Serialization/deserialization

Run with: pytest tests/test_intent_tracker.py -v
"""

import pytest
from datetime import datetime

from src.intent_tracker import (
    IntentTracker,
    IntentRecord,
    INTENT_CATEGORIES
)


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def tracker():
    """Create a fresh IntentTracker for each test."""
    return IntentTracker()


@pytest.fixture
def populated_tracker():
    """Create tracker with some recorded intents."""
    tracker = IntentTracker()
    tracker.record("greeting", "greeting")
    tracker.record("price_question", "spin_situation")
    tracker.record("price_question", "spin_situation")
    return tracker


# =============================================================================
# INTENT_CATEGORIES TESTS
# =============================================================================

class TestIntentCategories:
    """Tests for INTENT_CATEGORIES constant."""

    def test_categories_exist(self):
        """Test that all expected categories exist."""
        expected_categories = ["objection", "positive", "question", "spin_progress", "negative"]
        for cat in expected_categories:
            assert cat in INTENT_CATEGORIES

    def test_all_new_categories_exist(self):
        """Test that all 26 categories from constants.yaml are loaded."""
        expected_new_categories = [
            "objection", "positive", "question", "spin_progress", "negative",
            "price_related", "question_requires_facts", "informative",
            "equipment_questions", "tariff_questions", "tis_questions",
            "tax_questions", "accounting_questions", "integration_specific",
            "operations_questions", "delivery_service", "business_scenarios",
            "technical_problems", "conversational", "fiscal_questions",
            "analytics_questions", "wipon_products", "employee_questions",
            "promo_loyalty", "stability_questions", "region_questions",
            "additional_integrations", "purchase_stages", "company_info",
            "dialogue_control"
        ]
        for cat in expected_new_categories:
            assert cat in INTENT_CATEGORIES, f"Category '{cat}' not found in INTENT_CATEGORIES"

    def test_equipment_questions_category(self):
        """Test equipment_questions category (12 intents)."""
        equipment_intents = INTENT_CATEGORIES.get("equipment_questions", [])
        assert len(equipment_intents) >= 12, f"Expected >= 12 equipment intents, got {len(equipment_intents)}"
        assert "question_pos_monoblock" in equipment_intents
        assert "question_scales" in equipment_intents
        assert "question_scanner" in equipment_intents
        assert "question_printer" in equipment_intents

    def test_tariff_questions_category(self):
        """Test tariff_questions category (8 intents)."""
        tariff_intents = INTENT_CATEGORIES.get("tariff_questions", [])
        assert len(tariff_intents) >= 8
        assert "question_tariff_mini" in tariff_intents
        assert "question_tariff_comparison" in tariff_intents

    def test_tis_questions_category(self):
        """Test tis_questions category (10 intents)."""
        tis_intents = INTENT_CATEGORIES.get("tis_questions", [])
        assert len(tis_intents) >= 10
        assert "question_tis_general" in tis_intents
        assert "question_tis_2026" in tis_intents

    def test_business_scenarios_category(self):
        """Test business_scenarios category (18 intents)."""
        scenarios = INTENT_CATEGORIES.get("business_scenarios", [])
        assert len(scenarios) >= 18, f"Expected >= 18 business scenarios, got {len(scenarios)}"
        assert "question_grocery_store" in scenarios
        assert "question_restaurant_cafe" in scenarios
        assert "question_pharmacy" in scenarios

    def test_technical_problems_category(self):
        """Test technical_problems category (6 intents)."""
        problems = INTENT_CATEGORIES.get("technical_problems", [])
        assert len(problems) >= 6
        assert "problem_technical" in problems
        assert "problem_connection" in problems

    def test_conversational_category(self):
        """Test conversational category (10 intents)."""
        conversational = INTENT_CATEGORIES.get("conversational", [])
        assert len(conversational) >= 10
        assert "compliment" in conversational
        assert "frustration_expression" in conversational

    def test_purchase_stages_category(self):
        """Test purchase_stages category (8 intents)."""
        purchase = INTENT_CATEGORIES.get("purchase_stages", [])
        assert len(purchase) >= 8
        assert "request_proposal" in purchase
        assert "request_contract" in purchase

    def test_dialogue_control_category(self):
        """Test dialogue_control category (8 intents)."""
        dialogue = INTENT_CATEGORIES.get("dialogue_control", [])
        assert len(dialogue) >= 8
        assert "go_back" in dialogue
        assert "clarification_request" in dialogue

    def test_informative_category(self):
        """Test informative category."""
        informative = INTENT_CATEGORIES.get("informative", [])
        assert len(informative) > 0
        assert "situation_provided" in informative
        assert "problem_revealed" in informative
        assert "info_provided" in informative

    def test_objection_category(self):
        """Test objection category contents."""
        objection_intents = INTENT_CATEGORIES["objection"]
        assert "objection_price" in objection_intents
        assert "objection_competitor" in objection_intents
        assert "objection_no_time" in objection_intents
        assert "objection_think" in objection_intents

    def test_positive_category(self):
        """Test positive category contents."""
        positive_intents = INTENT_CATEGORIES["positive"]
        assert "agreement" in positive_intents
        assert "demo_request" in positive_intents
        assert "greeting" in positive_intents

    def test_question_category(self):
        """Test question category contents."""
        question_intents = INTENT_CATEGORIES["question"]
        assert "price_question" in question_intents
        assert "question_features" in question_intents
        assert "question_technical" in question_intents

    def test_spin_progress_category(self):
        """Test spin_progress category contents."""
        spin_intents = INTENT_CATEGORIES["spin_progress"]
        assert "situation_provided" in spin_intents
        assert "problem_revealed" in spin_intents
        assert "implication_acknowledged" in spin_intents
        assert "need_expressed" in spin_intents

    def test_negative_category(self):
        """Test negative category contains rejections and objections."""
        negative_intents = INTENT_CATEGORIES["negative"]
        assert "rejection" in negative_intents
        assert "farewell" in negative_intents

    def test_total_intents_count(self):
        """Test that we have 150+ unique intents across all categories."""
        all_intents = set()
        for category_intents in INTENT_CATEGORIES.values():
            all_intents.update(category_intents)
        assert len(all_intents) >= 150, f"Expected >= 150 unique intents, got {len(all_intents)}"


# =============================================================================
# INTENT RECORD TESTS
# =============================================================================

class TestIntentRecord:
    """Tests for IntentRecord dataclass."""

    def test_create_record(self):
        """Test creating an IntentRecord."""
        record = IntentRecord(
            intent="greeting",
            state="greeting",
            turn_number=0
        )
        assert record.intent == "greeting"
        assert record.state == "greeting"
        assert record.turn_number == 0
        assert isinstance(record.timestamp, datetime)

    def test_record_to_dict(self):
        """Test converting record to dictionary."""
        record = IntentRecord(
            intent="price_question",
            state="spin_situation",
            turn_number=5
        )
        data = record.to_dict()

        assert data["intent"] == "price_question"
        assert data["state"] == "spin_situation"
        assert data["turn_number"] == 5
        assert "timestamp" in data

    def test_record_with_custom_timestamp(self):
        """Test record with custom timestamp."""
        ts = datetime(2025, 1, 1, 12, 0, 0)
        record = IntentRecord(
            intent="test",
            state="test",
            timestamp=ts
        )
        assert record.timestamp == ts


# =============================================================================
# INTENT TRACKER BASIC TESTS
# =============================================================================

class TestIntentTrackerBasic:
    """Basic tests for IntentTracker."""

    def test_initial_state(self, tracker):
        """Test tracker initial state."""
        assert tracker.last_intent is None
        assert tracker.prev_intent is None
        assert tracker.last_state is None
        assert tracker.history_length == 0
        assert tracker.turn_number == 0

    def test_record_single_intent(self, tracker):
        """Test recording a single intent."""
        tracker.record("greeting", "greeting")

        assert tracker.last_intent == "greeting"
        assert tracker.prev_intent is None
        assert tracker.last_state == "greeting"
        assert tracker.history_length == 1
        assert tracker.turn_number == 1

    def test_record_multiple_intents(self, tracker):
        """Test recording multiple intents."""
        tracker.record("greeting", "greeting")
        tracker.record("price_question", "spin_situation")
        tracker.record("agreement", "close")

        assert tracker.last_intent == "agreement"
        assert tracker.prev_intent == "price_question"
        assert tracker.last_state == "close"
        assert tracker.history_length == 3
        assert tracker.turn_number == 3

    def test_reset(self, populated_tracker):
        """Test resetting tracker."""
        populated_tracker.reset()

        assert populated_tracker.last_intent is None
        assert populated_tracker.prev_intent is None
        assert populated_tracker.history_length == 0
        assert populated_tracker.turn_number == 0


# =============================================================================
# STREAK COUNTING TESTS
# =============================================================================

class TestStreakCounting:
    """Tests for streak counting functionality."""

    def test_streak_single_intent(self, tracker):
        """Test streak for single intent."""
        tracker.record("price_question", "spin_situation")
        assert tracker.streak_count("price_question") == 1

    def test_streak_consecutive_same_intent(self, tracker):
        """Test streak for consecutive same intents."""
        tracker.record("price_question", "spin_situation")
        tracker.record("price_question", "spin_situation")
        tracker.record("price_question", "spin_situation")

        assert tracker.streak_count("price_question") == 3

    def test_streak_breaks_on_different_intent(self, tracker):
        """Test streak breaks when different intent recorded."""
        tracker.record("price_question", "spin_situation")
        tracker.record("price_question", "spin_situation")
        tracker.record("agreement", "close")

        assert tracker.streak_count("price_question") == 0
        assert tracker.streak_count("agreement") == 1

    def test_streak_for_nonexistent_intent(self, tracker):
        """Test streak returns 0 for unrecorded intent."""
        tracker.record("greeting", "greeting")
        assert tracker.streak_count("price_question") == 0

    def test_streak_restarts_after_break(self, tracker):
        """Test streak restarts after break."""
        tracker.record("price_question", "spin_situation")
        tracker.record("price_question", "spin_situation")
        tracker.record("agreement", "close")
        tracker.record("price_question", "presentation")
        tracker.record("price_question", "presentation")

        assert tracker.streak_count("price_question") == 2


# =============================================================================
# TOTAL COUNTING TESTS
# =============================================================================

class TestTotalCounting:
    """Tests for total counting functionality."""

    def test_total_single_intent(self, tracker):
        """Test total count for single intent."""
        tracker.record("greeting", "greeting")
        assert tracker.total_count("greeting") == 1

    def test_total_multiple_same_intent(self, tracker):
        """Test total count for multiple same intents."""
        tracker.record("price_question", "spin_situation")
        tracker.record("agreement", "close")
        tracker.record("price_question", "presentation")

        assert tracker.total_count("price_question") == 2

    def test_total_for_nonexistent_intent(self, tracker):
        """Test total returns 0 for unrecorded intent."""
        assert tracker.total_count("never_recorded") == 0


# =============================================================================
# CATEGORY TRACKING TESTS
# =============================================================================

class TestCategoryTracking:
    """Tests for category tracking functionality."""

    def test_category_total_objections(self, tracker):
        """Test total count for objection category."""
        tracker.record("objection_price", "handle_objection")
        tracker.record("objection_competitor", "handle_objection")
        tracker.record("objection_price", "handle_objection")

        assert tracker.category_total("objection") == 3

    def test_category_streak_objections(self, tracker):
        """Test streak count for objection category."""
        tracker.record("objection_price", "handle_objection")
        tracker.record("objection_competitor", "handle_objection")
        tracker.record("objection_no_time", "handle_objection")

        assert tracker.category_streak("objection") == 3

    def test_category_streak_breaks_on_other_category(self, tracker):
        """Test category streak breaks on different category."""
        tracker.record("objection_price", "handle_objection")
        tracker.record("objection_price", "handle_objection")
        tracker.record("agreement", "close")

        assert tracker.category_streak("objection") == 0
        assert tracker.category_streak("positive") == 1

    def test_category_total_questions(self, tracker):
        """Test total count for question category."""
        tracker.record("price_question", "spin_situation")
        tracker.record("question_features", "spin_situation")

        assert tracker.category_total("question") == 2

    def test_category_for_nonexistent(self, tracker):
        """Test category counts for nonexistent category."""
        tracker.record("greeting", "greeting")
        assert tracker.category_total("nonexistent") == 0
        assert tracker.category_streak("nonexistent") == 0


# =============================================================================
# OBJECTION FLOW MANAGER REPLACEMENT TESTS
# =============================================================================

class TestObjectionFlowManagerReplacement:
    """Tests for methods replacing ObjectionFlowManager."""

    def test_objection_consecutive(self, tracker):
        """Test objection_consecutive method."""
        tracker.record("objection_price", "handle_objection")
        tracker.record("objection_competitor", "handle_objection")

        assert tracker.objection_consecutive() == 2

    def test_objection_total(self, tracker):
        """Test objection_total method."""
        tracker.record("objection_price", "handle_objection")
        tracker.record("agreement", "close")
        tracker.record("objection_think", "soft_close")

        assert tracker.objection_total() == 2

    def test_is_objection(self, tracker):
        """Test is_objection helper."""
        assert tracker.is_objection("objection_price") is True
        assert tracker.is_objection("objection_competitor") is True
        assert tracker.is_objection("agreement") is False

    def test_is_positive(self, tracker):
        """Test is_positive helper."""
        assert tracker.is_positive("agreement") is True
        assert tracker.is_positive("demo_request") is True
        assert tracker.is_positive("objection_price") is False

    def test_is_question(self, tracker):
        """Test is_question helper."""
        assert tracker.is_question("price_question") is True
        assert tracker.is_question("question_technical") is True
        assert tracker.is_question("agreement") is False

    def test_is_spin_progress(self, tracker):
        """Test is_spin_progress helper."""
        assert tracker.is_spin_progress("situation_provided") is True
        assert tracker.is_spin_progress("problem_revealed") is True
        assert tracker.is_spin_progress("greeting") is False


# =============================================================================
# HISTORY TESTS
# =============================================================================

class TestHistory:
    """Tests for history functionality."""

    def test_get_history_all(self, populated_tracker):
        """Test getting all history."""
        history = populated_tracker.get_history()
        assert len(history) == 3

    def test_get_history_limited(self, populated_tracker):
        """Test getting limited history."""
        history = populated_tracker.get_history(limit=2)
        assert len(history) == 2
        assert history[-1].intent == "price_question"

    def test_get_recent_intents(self, populated_tracker):
        """Test getting recent intent names."""
        recent = populated_tracker.get_recent_intents(limit=2)
        assert recent == ["price_question", "price_question"]

    def test_get_intents_by_category(self, tracker):
        """Test getting records by category."""
        tracker.record("price_question", "spin_situation")
        tracker.record("agreement", "close")
        tracker.record("question_features", "spin_situation")

        questions = tracker.get_intents_by_category("question")
        assert len(questions) == 2

    def test_get_state_history(self, populated_tracker):
        """Test getting state history."""
        states = populated_tracker.get_state_history()
        assert states == ["greeting", "spin_situation", "spin_situation"]


# =============================================================================
# SERIALIZATION TESTS
# =============================================================================

class TestSerialization:
    """Tests for serialization functionality."""

    def test_to_dict(self, populated_tracker):
        """Test converting tracker to dict."""
        data = populated_tracker.to_dict()

        assert data["last_intent"] == "price_question"
        assert data["prev_intent"] == "price_question"
        assert data["current_streak"]["intent"] == "price_question"
        assert data["current_streak"]["count"] == 2
        assert data["turn_number"] == 3
        assert "intent_totals" in data
        assert "category_totals" in data

    def test_to_compact_dict(self, populated_tracker):
        """Test converting to compact dict."""
        data = populated_tracker.to_compact_dict()

        assert data["last"] == "price_question"
        assert data["prev"] == "price_question"
        assert data["streak"] == ("price_question", 2)
        assert data["turn"] == 3

    def test_from_dict(self):
        """Test creating tracker from dict."""
        data = {
            "current_streak": {"intent": "price_question", "count": 3},
            "turn_number": 5,
            "intent_totals": {"price_question": 3, "greeting": 1},
            "category_totals": {"question": 3, "positive": 1},
            "category_streaks": {"question": 3}
        }

        tracker = IntentTracker.from_dict(data)

        assert tracker.streak_count("price_question") == 3
        assert tracker.turn_number == 5
        assert tracker.total_count("price_question") == 3

    def test_from_dict_empty(self):
        """Test creating tracker from empty dict."""
        tracker = IntentTracker.from_dict({})

        assert tracker.last_intent is None
        assert tracker.turn_number == 0


# =============================================================================
# REPR AND STR TESTS
# =============================================================================

class TestRepr:
    """Tests for __repr__ method."""

    def test_repr_empty(self, tracker):
        """Test repr for empty tracker."""
        repr_str = repr(tracker)
        assert "IntentTracker" in repr_str
        assert "last=None" in repr_str

    def test_repr_with_data(self, populated_tracker):
        """Test repr with recorded intents."""
        repr_str = repr(populated_tracker)
        assert "IntentTracker" in repr_str
        assert "price_question" in repr_str
        assert "streak=2" in repr_str


# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases."""

    def test_intent_in_multiple_categories(self, tracker):
        """Test intent that belongs to multiple categories."""
        # question_features is in both "positive" and "question"
        tracker.record("question_features", "spin_situation")

        assert tracker.category_total("positive") == 1
        assert tracker.category_total("question") == 1

    def test_empty_history_operations(self, tracker):
        """Test operations on empty tracker."""
        assert tracker.get_history() == []
        assert tracker.get_recent_intents() == []
        assert tracker.get_state_history() == []

    def test_large_number_of_records(self, tracker):
        """Test with large number of records."""
        for i in range(100):
            tracker.record("price_question" if i % 2 == 0 else "agreement", "state")

        assert tracker.history_length == 100
        assert tracker.total_count("price_question") == 50
        assert tracker.total_count("agreement") == 50

    def test_category_with_no_matching_intents(self, tracker):
        """Test category tracking with no matching intents."""
        tracker.record("unclear", "greeting")  # Not in any category

        assert tracker.category_total("objection") == 0
        assert tracker.category_streak("objection") == 0


# =============================================================================
# NEW CATEGORY HELPER METHODS TESTS
# =============================================================================

class TestNewCategoryHelperMethods:
    """Tests for new category helper methods (150+ intents support)."""

    def test_is_in_category(self, tracker):
        """Test universal is_in_category method."""
        assert tracker.is_in_category("question_pos_monoblock", "equipment_questions") is True
        assert tracker.is_in_category("question_grocery_store", "business_scenarios") is True
        assert tracker.is_in_category("objection_price", "equipment_questions") is False

    def test_equipment_questions_helpers(self, tracker):
        """Test equipment questions helper methods."""
        tracker.record("question_pos_monoblock", "spin_situation")
        tracker.record("question_scales", "spin_situation")
        tracker.record("question_scanner", "spin_situation")

        assert tracker.is_equipment_question("question_pos_monoblock") is True
        assert tracker.is_equipment_question("price_question") is False
        assert tracker.equipment_questions_total() == 3
        assert tracker.equipment_questions_streak() == 3

    def test_tariff_questions_helpers(self, tracker):
        """Test tariff questions helper methods."""
        tracker.record("question_tariff_mini", "spin_situation")
        tracker.record("question_tariff_comparison", "spin_situation")

        assert tracker.is_tariff_question("question_tariff_mini") is True
        assert tracker.tariff_questions_total() == 2
        assert tracker.tariff_questions_streak() == 2

    def test_tis_questions_helpers(self, tracker):
        """Test TIS questions helper methods."""
        tracker.record("question_tis_general", "spin_situation")
        tracker.record("question_tis_2026", "spin_situation")

        assert tracker.is_tis_question("question_tis_general") is True
        assert tracker.tis_questions_total() == 2

    def test_business_scenario_helpers(self, tracker):
        """Test business scenario helper methods."""
        tracker.record("question_grocery_store", "spin_situation")
        tracker.record("question_restaurant_cafe", "spin_situation")

        assert tracker.is_business_scenario("question_grocery_store") is True
        assert tracker.is_business_scenario("price_question") is False
        assert tracker.business_scenarios_total() == 2

    def test_technical_problems_helpers(self, tracker):
        """Test technical problems helper methods."""
        tracker.record("problem_technical", "handle_objection")
        tracker.record("problem_connection", "handle_objection")

        assert tracker.is_technical_problem("problem_technical") is True
        assert tracker.technical_problems_total() == 2

    def test_conversational_helpers(self, tracker):
        """Test conversational intents helper methods."""
        tracker.record("compliment", "greeting")
        tracker.record("frustration_expression", "spin_situation")

        assert tracker.is_conversational("compliment") is True
        assert tracker.conversational_total() == 2

    def test_informative_helpers(self, tracker):
        """Test informative intents helper methods."""
        tracker.record("situation_provided", "spin_situation")
        tracker.record("info_provided", "spin_situation")

        assert tracker.is_informative("situation_provided") is True
        assert tracker.informative_total() == 2

    def test_purchase_stages_helpers(self, tracker):
        """Test purchase stages helper methods."""
        tracker.record("request_proposal", "close")
        tracker.record("request_contract", "close")

        assert tracker.is_purchase_stage("request_proposal") is True
        assert tracker.purchase_stages_total() == 2

    def test_dialogue_control_helpers(self, tracker):
        """Test dialogue control helper methods."""
        tracker.record("go_back", "spin_problem")
        tracker.record("clarification_request", "spin_problem")

        assert tracker.is_dialogue_control("go_back") is True
        assert tracker.dialogue_control_total() == 2

    def test_price_related_helpers(self, tracker):
        """Test price-related intents helper methods."""
        tracker.record("price_question", "spin_situation")
        tracker.record("pricing_details", "spin_situation")

        assert tracker.is_price_related("price_question") is True
        assert tracker.price_related_total() == 2

    def test_negative_helpers(self, tracker):
        """Test negative intents helper methods."""
        tracker.record("rejection", "close")
        tracker.record("objection_price", "handle_objection")

        assert tracker.is_negative("rejection") is True
        assert tracker.negative_total() == 2


class TestPatternDetection:
    """Tests for pattern detection across new categories."""

    def test_get_category_counts(self, tracker):
        """Test get_category_counts returns all categories."""
        tracker.record("question_pos_monoblock", "spin_situation")
        tracker.record("question_grocery_store", "spin_situation")
        tracker.record("objection_price", "handle_objection")

        counts = tracker.get_category_counts()
        assert isinstance(counts, dict)
        assert "equipment_questions" in counts
        assert "business_scenarios" in counts
        assert "objection" in counts
        assert counts["equipment_questions"] == 1
        assert counts["business_scenarios"] == 1

    def test_get_active_categories(self, tracker):
        """Test get_active_categories finds categories with activity."""
        tracker.record("question_pos_monoblock", "spin_situation")
        tracker.record("question_pos_monoblock", "spin_situation")
        tracker.record("question_grocery_store", "spin_situation")

        active = tracker.get_active_categories(min_count=1)
        assert "equipment_questions" in active
        assert "business_scenarios" in active

        active_2 = tracker.get_active_categories(min_count=2)
        assert "equipment_questions" in active_2
        # business_scenarios has only 1 occurrence
        assert "business_scenarios" not in active_2

    def test_has_pattern_total(self, tracker):
        """Test has_pattern with min_total."""
        tracker.record("question_pos_monoblock", "spin_situation")
        tracker.record("question_scales", "spin_situation")
        tracker.record("question_scanner", "spin_situation")

        # 3 equipment questions total
        assert tracker.has_pattern("equipment_questions", min_total=3) is True
        assert tracker.has_pattern("equipment_questions", min_total=4) is False

    def test_has_pattern_streak(self, tracker):
        """Test has_pattern with min_streak."""
        tracker.record("objection_price", "handle_objection")
        tracker.record("objection_competitor", "handle_objection")
        tracker.record("objection_no_time", "handle_objection")

        # 3 consecutive objections
        assert tracker.has_pattern("objection", min_streak=3) is True
        assert tracker.has_pattern("objection", min_streak=4) is False

    def test_has_pattern_combined(self, tracker):
        """Test has_pattern with both min_total and min_streak."""
        tracker.record("question_pos_monoblock", "spin_situation")
        tracker.record("question_scales", "spin_situation")
        tracker.record("question_scanner", "spin_situation")

        # Both conditions must be met
        assert tracker.has_pattern("equipment_questions", min_total=3, min_streak=3) is True
        assert tracker.has_pattern("equipment_questions", min_total=3, min_streak=4) is False

    def test_equipment_questions_pattern_scenario(self, tracker):
        """Test real scenario: client asked about equipment 3 times."""
        # Scenario from the task: "клиент 3 раза спросил про оборудование"
        tracker.record("greeting", "greeting")
        tracker.record("question_pos_monoblock", "spin_situation")
        tracker.record("situation_provided", "spin_situation")
        tracker.record("question_scales", "spin_problem")
        tracker.record("question_printer", "spin_problem")

        # Should detect equipment questions pattern
        assert tracker.equipment_questions_total() == 3
        assert tracker.has_pattern("equipment_questions", min_total=3) is True


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests for realistic scenarios."""

    def test_price_escalation_scenario(self, tracker):
        """Test price question escalation scenario from plan."""
        # Scenario: price_question repeated 3x should trigger escalation
        tracker.record("greeting", "greeting")
        tracker.record("price_question", "spin_situation")
        tracker.record("price_question", "spin_situation")
        tracker.record("price_question", "spin_situation")

        # Should have 3 consecutive price questions
        assert tracker.streak_count("price_question") >= 3

    def test_objection_limit_scenario(self, tracker):
        """Test objection limit scenario from plan."""
        # Scenario: 3 consecutive objections or 5 total
        tracker.record("objection_price", "handle_objection")
        tracker.record("objection_competitor", "handle_objection")
        tracker.record("objection_no_time", "handle_objection")

        # 3 consecutive objections
        assert tracker.objection_consecutive() >= 3

    def test_mixed_conversation_flow(self, tracker):
        """Test realistic mixed conversation flow."""
        # Realistic conversation: greeting -> questions -> objection -> agreement
        tracker.record("greeting", "greeting")
        tracker.record("price_question", "spin_situation")
        tracker.record("question_features", "spin_situation")
        tracker.record("objection_price", "handle_objection")
        tracker.record("agreement", "close")

        assert tracker.total_count("greeting") == 1
        assert tracker.category_total("question") == 2
        assert tracker.objection_total() == 1
        assert tracker.last_intent == "agreement"
        assert tracker.is_positive(tracker.last_intent)

    def test_equipment_focused_customer(self, tracker):
        """Test scenario: customer focused on equipment questions."""
        tracker.record("greeting", "greeting")
        tracker.record("question_pos_monoblock", "spin_situation")
        tracker.record("question_scales", "spin_situation")
        tracker.record("question_scanner", "spin_situation")
        tracker.record("question_equipment_bundle", "presentation")

        assert tracker.equipment_questions_total() == 4
        assert tracker.has_pattern("equipment_questions", min_total=3) is True

    def test_business_scenario_conversation(self, tracker):
        """Test scenario: customer asking about specific business type."""
        tracker.record("greeting", "greeting")
        tracker.record("question_grocery_store", "spin_situation")
        tracker.record("situation_provided", "spin_situation")
        tracker.record("question_grocery_store", "spin_problem")

        assert tracker.business_scenarios_total() == 2
        assert tracker.is_business_scenario("question_grocery_store") is True

    def test_technical_support_escalation(self, tracker):
        """Test scenario: customer with technical problems."""
        tracker.record("greeting", "greeting")
        tracker.record("problem_technical", "spin_situation")
        tracker.record("frustration_expression", "spin_situation")
        tracker.record("problem_connection", "handle_objection")

        assert tracker.technical_problems_total() == 2
        assert tracker.conversational_total() == 1
        assert tracker.is_conversational("frustration_expression") is True
