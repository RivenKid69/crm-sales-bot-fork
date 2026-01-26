"""
Tests for Price Deflect Loop Bug Fix.

This test suite verifies the fix for the critical bug where price-related questions
caused an infinite deflect loop because:
1. price_repeated_3x condition only checked intent_streak("price_question")
2. When client asked different price-related questions (discount_request, pricing_details),
   the streak was reset and never reached 3

Bug scenario:
    Turn 1: "а какая цена?" -> price_question, streak=1
    Turn 2: "и скидка есть?" -> discount_request, streak=0 (RESET!)
    Turn 3: "не важно. скажи цену" -> price_question, streak=1 (RESTART!)
    ... infinite loop ...

Fix:
1. conditions.py: price_repeated_3x/2x now use get_category_streak("price_related")
2. constants.yaml: price_related category expanded from 2 to 7 intents
3. PriceQuestionSource: now imports intents from constants.yaml (Single Source of Truth)
4. EscalationSource: now imports intents from constants.yaml

Run with: pytest tests/test_price_deflect_loop_fix.py -v
"""

import pytest
from unittest.mock import MagicMock, patch

from src.intent_tracker import IntentTracker, INTENT_CATEGORIES
from src.yaml_config.constants import PRICE_RELATED_INTENTS


# =============================================================================
# CATEGORY SYNCHRONIZATION TESTS
# =============================================================================

class TestPriceRelatedCategorySync:
    """Tests for price_related category synchronization across components."""

    def test_price_related_category_has_7_intents(self):
        """Verify price_related category contains all 7 intents."""
        price_intents = INTENT_CATEGORIES.get("price_related", [])
        expected_intents = {
            "price_question",
            "pricing_details",
            "cost_inquiry",
            "discount_request",
            "payment_terms",
            "pricing_comparison",
            "budget_question",
        }
        assert len(price_intents) == 7, f"Expected 7 intents, got {len(price_intents)}"
        assert set(price_intents) == expected_intents

    def test_price_related_constants_export(self):
        """Verify PRICE_RELATED_INTENTS constant is exported correctly."""
        assert len(PRICE_RELATED_INTENTS) == 7
        assert "price_question" in PRICE_RELATED_INTENTS
        assert "discount_request" in PRICE_RELATED_INTENTS

    def test_price_question_source_uses_constants(self):
        """Verify PriceQuestionSource imports from constants.yaml."""
        from src.blackboard.sources.price_question import PriceQuestionSource

        # Should match INTENT_CATEGORIES["price_related"]
        expected = set(INTENT_CATEGORIES.get("price_related", []))
        assert PriceQuestionSource.DEFAULT_PRICE_INTENTS == expected

    def test_escalation_source_uses_constants(self):
        """Verify EscalationSource imports from constants.yaml."""
        from src.blackboard.sources.escalation import EscalationSource

        # Check escalation category
        escalation_intents = set(INTENT_CATEGORIES.get("escalation", []))
        if escalation_intents:
            assert EscalationSource.EXPLICIT_ESCALATION_INTENTS == escalation_intents

        # Check frustration category
        frustration_intents = set(INTENT_CATEGORIES.get("frustration", []))
        if frustration_intents:
            assert EscalationSource.FRUSTRATION_INTENTS == frustration_intents

        # Check sensitive category
        sensitive_intents = set(INTENT_CATEGORIES.get("sensitive", []))
        if sensitive_intents:
            assert EscalationSource.SENSITIVE_INTENTS == sensitive_intents


# =============================================================================
# NEW CATEGORY TESTS
# =============================================================================

class TestNewCategories:
    """Tests for newly added categories in constants.yaml."""

    def test_escalation_category_exists(self):
        """Verify escalation category exists with 8 intents."""
        escalation = INTENT_CATEGORIES.get("escalation", [])
        assert len(escalation) == 8
        expected = {
            "request_human", "speak_to_manager", "talk_to_person", "need_help",
            "not_a_bot", "real_person", "human_please", "escalate",
        }
        assert set(escalation) == expected

    def test_frustration_category_exists(self):
        """Verify frustration category exists with 6 intents."""
        frustration = INTENT_CATEGORIES.get("frustration", [])
        assert len(frustration) == 6
        expected = {
            "frustrated", "angry", "complaint",
            "this_is_useless", "not_helpful", "waste_of_time",
        }
        assert set(frustration) == expected

    def test_sensitive_category_exists(self):
        """Verify sensitive category exists with 7 intents."""
        sensitive = INTENT_CATEGORIES.get("sensitive", [])
        assert len(sensitive) == 7
        expected = {
            "legal_question", "compliance_question", "formal_complaint",
            "refund_request", "contract_dispute", "data_deletion", "gdpr_request",
        }
        assert set(sensitive) == expected

    def test_technical_question_category_exists(self):
        """Verify technical_question category exists with correct intents."""
        tech = INTENT_CATEGORIES.get("technical_question", [])
        assert len(tech) >= 10  # At least 10 technical question intents
        assert "question_technical" in tech
        assert "question_security" in tech
        assert "question_support" in tech
        assert "question_implementation" in tech


# =============================================================================
# INTENT TRACKER CATEGORY STREAK TESTS
# =============================================================================

class TestCategoryStreakFix:
    """Tests for category streak behavior that fixes the deflect loop bug."""

    @pytest.fixture
    def tracker(self):
        """Create fresh IntentTracker."""
        return IntentTracker()

    def test_price_related_streak_accumulates_across_intents(self, tracker):
        """
        CRITICAL TEST: Verify category streak accumulates across different
        price-related intents.

        This is the core fix for the deflect loop bug.
        """
        # Simulate the bug scenario
        tracker.record("price_question", "spin_situation")  # Turn 1
        assert tracker.category_streak("price_related") == 1

        tracker.record("discount_request", "spin_situation")  # Turn 2
        # BUG FIX: This should be 2, not 0!
        assert tracker.category_streak("price_related") == 2

        tracker.record("pricing_details", "spin_situation")  # Turn 3
        # BUG FIX: This should be 3, triggering price_repeated_3x!
        assert tracker.category_streak("price_related") == 3

    def test_price_related_streak_resets_on_non_price_intent(self, tracker):
        """Verify streak resets when non-price intent is recorded."""
        tracker.record("price_question", "spin_situation")
        tracker.record("discount_request", "spin_situation")
        assert tracker.category_streak("price_related") == 2

        # Non-price intent should reset the streak
        tracker.record("agreement", "spin_situation")
        assert tracker.category_streak("price_related") == 0

    def test_full_deflect_loop_scenario_now_reaches_3(self, tracker):
        """
        Reproduce the exact bug scenario from the report.

        Original bug: Client asks about price 141 times, never triggers escalation.
        Fix: After 3 price-related intents, streak reaches 3.
        """
        # Exact scenario from bug report
        tracker.record("price_question", "spin_situation")  # "а какая цена?"
        tracker.record("discount_request", "spin_situation")  # "и скидка есть?"
        tracker.record("price_question", "spin_situation")  # "не важно. скажи цену"

        # With the fix, this should be 3
        assert tracker.category_streak("price_related") == 3

    def test_technical_question_streak_accumulates(self, tracker):
        """Verify technical_question category streak works correctly."""
        tracker.record("question_technical", "spin_situation")
        assert tracker.category_streak("technical_question") == 1

        tracker.record("question_security", "spin_situation")
        assert tracker.category_streak("technical_question") == 2

        tracker.record("question_support", "spin_situation")
        assert tracker.category_streak("technical_question") == 3

    def test_frustration_streak_accumulates(self, tracker):
        """Verify frustration category streak works correctly."""
        tracker.record("frustrated", "spin_situation")
        assert tracker.category_streak("frustration") == 1

        tracker.record("angry", "spin_situation")
        assert tracker.category_streak("frustration") == 2

        tracker.record("complaint", "spin_situation")
        assert tracker.category_streak("frustration") == 3


# =============================================================================
# CONDITIONS.PY TESTS
# =============================================================================

class TestConditionsFix:
    """Tests for fixed conditions in conditions.py."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock EvaluatorContext."""
        ctx = MagicMock()
        ctx.intent_tracker = IntentTracker()
        ctx.collected_data = {}
        ctx.current_intent = None

        # Setup get_category_streak to delegate to tracker
        def get_category_streak(category):
            return ctx.intent_tracker.category_streak(category)

        ctx.get_category_streak = get_category_streak
        return ctx

    def test_price_repeated_3x_uses_category_streak(self, mock_context):
        """Verify price_repeated_3x uses category_streak, not intent_streak."""
        from src.conditions.state_machine.conditions import price_repeated_3x

        # Record 3 different price-related intents
        mock_context.intent_tracker.record("price_question", "spin_situation")
        mock_context.intent_tracker.record("discount_request", "spin_situation")
        mock_context.intent_tracker.record("pricing_details", "spin_situation")

        # With the fix, this should be True
        assert price_repeated_3x(mock_context) is True

    def test_price_repeated_2x_uses_category_streak(self, mock_context):
        """Verify price_repeated_2x uses category_streak, not intent_streak."""
        from src.conditions.state_machine.conditions import price_repeated_2x

        # Record 2 different price-related intents
        mock_context.intent_tracker.record("price_question", "spin_situation")
        mock_context.intent_tracker.record("cost_inquiry", "spin_situation")

        # With the fix, this should be True
        assert price_repeated_2x(mock_context) is True

    def test_technical_question_repeated_2x_uses_category_streak(self, mock_context):
        """Verify technical_question_repeated_2x uses category_streak."""
        from src.conditions.state_machine.conditions import technical_question_repeated_2x

        # Record 2 different technical question intents
        mock_context.intent_tracker.record("question_technical", "spin_situation")
        mock_context.intent_tracker.record("question_security", "spin_situation")

        # With the fix, this should be True
        assert technical_question_repeated_2x(mock_context) is True

    def test_price_repeated_3x_false_when_interrupted(self, mock_context):
        """Verify price_repeated_3x is False when price streak is broken."""
        from src.conditions.state_machine.conditions import price_repeated_3x

        mock_context.intent_tracker.record("price_question", "spin_situation")
        mock_context.intent_tracker.record("discount_request", "spin_situation")
        mock_context.intent_tracker.record("agreement", "spin_situation")  # Breaks streak
        mock_context.intent_tracker.record("pricing_details", "spin_situation")

        # Streak was broken, should be False
        assert price_repeated_3x(mock_context) is False


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests verifying the full fix works end-to-end."""

    def test_all_price_intents_in_same_category(self):
        """Verify all price intents belong to price_related category."""
        tracker = IntentTracker()

        price_intents = [
            "price_question",
            "pricing_details",
            "cost_inquiry",
            "discount_request",
            "payment_terms",
            "pricing_comparison",
            "budget_question",
        ]

        for i, intent in enumerate(price_intents):
            tracker.record(intent, "test_state")
            # Each price intent should increment the category streak
            assert tracker.category_streak("price_related") == i + 1, \
                f"After {intent}, streak should be {i + 1}"

    def test_single_source_of_truth_principle(self):
        """
        Verify Single Source of Truth principle:
        constants.yaml defines categories, all components use them.
        """
        from src.blackboard.sources.price_question import PriceQuestionSource
        from src.blackboard.sources.escalation import EscalationSource

        # All should reference the same categories from constants.yaml
        yaml_price_related = set(INTENT_CATEGORIES.get("price_related", []))
        yaml_escalation = set(INTENT_CATEGORIES.get("escalation", []))
        yaml_frustration = set(INTENT_CATEGORIES.get("frustration", []))
        yaml_sensitive = set(INTENT_CATEGORIES.get("sensitive", []))

        # PriceQuestionSource should match
        assert PriceQuestionSource.DEFAULT_PRICE_INTENTS == yaml_price_related

        # EscalationSource should match (if categories exist)
        if yaml_escalation:
            assert EscalationSource.EXPLICIT_ESCALATION_INTENTS == yaml_escalation
        if yaml_frustration:
            assert EscalationSource.FRUSTRATION_INTENTS == yaml_frustration
        if yaml_sensitive:
            assert EscalationSource.SENSITIVE_INTENTS == yaml_sensitive


# =============================================================================
# REGRESSION TESTS
# =============================================================================

class TestRegression:
    """Regression tests to ensure the fix doesn't break existing behavior."""

    def test_objection_category_still_works(self):
        """Verify objection category tracking still works (already correct)."""
        tracker = IntentTracker()

        tracker.record("objection_price", "handle_objection")
        tracker.record("objection_competitor", "handle_objection")
        tracker.record("objection_no_time", "handle_objection")

        assert tracker.category_streak("objection") == 3
        assert tracker.category_total("objection") == 3

    def test_intent_streak_still_works(self):
        """Verify intent_streak still works for exact intent matching."""
        tracker = IntentTracker()

        tracker.record("price_question", "spin_situation")
        tracker.record("price_question", "spin_situation")
        tracker.record("price_question", "spin_situation")

        # Intent streak should still track exact matches
        assert tracker.streak_count("price_question") == 3
        # Category streak should also be 3
        assert tracker.category_streak("price_related") == 3

    def test_negative_composed_category_still_works(self):
        """Verify composed category 'negative' (objection + exit) still works."""
        # negative should be a composed category from objection + exit
        negative = INTENT_CATEGORIES.get("negative", [])
        objection = INTENT_CATEGORIES.get("objection", [])
        exit_intents = INTENT_CATEGORIES.get("exit", [])

        # All objection intents should be in negative
        for intent in objection:
            assert intent in negative, f"{intent} should be in negative category"

        # All exit intents should be in negative
        for intent in exit_intents:
            assert intent in negative, f"{intent} should be in negative category"
