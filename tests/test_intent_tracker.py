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
