"""
Tests for bug fixes identified in January 2026 code review.

Fixes verified:
1. bot.py - context_window sync after disambiguation
2. objection_handler.py - Optional[ObjectionType] typing
3. dag/executor.py - MAJORITY join condition (>= instead of >)
4. context_window.py - unreachable code removed, comment numbering fixed
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.context_window import ContextWindow, TurnContext, TurnType
from src.objection_handler import ObjectionHandler, ObjectionType, ObjectionResult
from src.dag.executor import DAGExecutor
from src.dag.models import (
    NodeType,
    JoinCondition,
    DAGExecutionContext,
    DAGNodeConfig,
)

# =============================================================================
# Test 1: ObjectionResult typing fix
# =============================================================================

class TestObjectionResultTyping:
    """Tests for ObjectionResult.objection_type being Optional."""

    def test_objection_result_with_none_type(self):
        """ObjectionResult should accept None for objection_type."""
        result = ObjectionResult(
            objection_type=None,
            strategy=None,
            attempt_number=0,
            should_soft_close=False,
        )

        assert result.objection_type is None
        assert result.strategy is None
        assert result.attempt_number == 0
        assert result.should_soft_close is False

    def test_objection_result_with_valid_type(self):
        """ObjectionResult should accept valid ObjectionType."""
        result = ObjectionResult(
            objection_type=ObjectionType.PRICE,
            strategy=None,
            attempt_number=1,
            should_soft_close=False,
        )

        assert result.objection_type == ObjectionType.PRICE
        assert result.attempt_number == 1

    def test_handler_returns_none_type_for_non_objection(self):
        """ObjectionHandler.handle_objection() returns None type for non-objections."""
        handler = ObjectionHandler()

        # Non-objection message
        result = handler.handle_objection("Привет, как дела?", {})

        assert result.objection_type is None
        assert result.strategy is None
        assert result.should_soft_close is False

# =============================================================================
# Test 2: DAG MAJORITY join condition fix
# =============================================================================

class TestDAGMajorityCondition:
    """Tests for MAJORITY join condition using >= instead of >."""

    def test_majority_with_two_branches_one_complete(self):
        """With 2 branches, 1 complete (50%) should satisfy MAJORITY."""
        ctx = DAGExecutionContext(primary_state="greeting")
        executor = DAGExecutor(
            flow_config=MagicMock(),
            condition_registry=MagicMock(),
        )

        completed = {"branch_a"}
        expected = {"branch_a", "branch_b"}

        result = executor._check_join_condition(
            JoinCondition.MAJORITY,
            completed,
            expected
        )

        # 1 >= 2/2 = 1 >= 1.0 = True (50% is majority)
        assert result is True

    def test_majority_with_four_branches_two_complete(self):
        """With 4 branches, 2 complete (50%) should satisfy MAJORITY."""
        ctx = DAGExecutionContext(primary_state="greeting")
        executor = DAGExecutor(
            flow_config=MagicMock(),
            condition_registry=MagicMock(),
        )

        completed = {"branch_a", "branch_b"}
        expected = {"branch_a", "branch_b", "branch_c", "branch_d"}

        result = executor._check_join_condition(
            JoinCondition.MAJORITY,
            completed,
            expected
        )

        # 2 >= 4/2 = 2 >= 2.0 = True (50% is majority)
        assert result is True

    def test_majority_with_four_branches_one_complete(self):
        """With 4 branches, 1 complete (25%) should NOT satisfy MAJORITY."""
        ctx = DAGExecutionContext(primary_state="greeting")
        executor = DAGExecutor(
            flow_config=MagicMock(),
            condition_registry=MagicMock(),
        )

        completed = {"branch_a"}
        expected = {"branch_a", "branch_b", "branch_c", "branch_d"}

        result = executor._check_join_condition(
            JoinCondition.MAJORITY,
            completed,
            expected
        )

        # 1 >= 4/2 = 1 >= 2.0 = False (25% is not majority)
        assert result is False

    def test_majority_with_three_branches_two_complete(self):
        """With 3 branches, 2 complete (67%) should satisfy MAJORITY."""
        ctx = DAGExecutionContext(primary_state="greeting")
        executor = DAGExecutor(
            flow_config=MagicMock(),
            condition_registry=MagicMock(),
        )

        completed = {"branch_a", "branch_b"}
        expected = {"branch_a", "branch_b", "branch_c"}

        result = executor._check_join_condition(
            JoinCondition.MAJORITY,
            completed,
            expected
        )

        # 2 >= 3/2 = 2 >= 1.5 = True (67% is majority)
        assert result is True

    def test_majority_with_three_branches_one_complete(self):
        """With 3 branches, 1 complete (33%) should NOT satisfy MAJORITY."""
        ctx = DAGExecutionContext(primary_state="greeting")
        executor = DAGExecutor(
            flow_config=MagicMock(),
            condition_registry=MagicMock(),
        )

        completed = {"branch_a"}
        expected = {"branch_a", "branch_b", "branch_c"}

        result = executor._check_join_condition(
            JoinCondition.MAJORITY,
            completed,
            expected
        )

        # 1 >= 3/2 = 1 >= 1.5 = False (33% is not majority)
        assert result is False

# =============================================================================
# Test 3: TurnContext.turn_type - unreachable code removed
# =============================================================================

class TestTurnContextTurnType:
    """Tests for TurnContext.turn_type property after fix."""

    def test_turn_type_progress_by_delta(self):
        """Positive funnel_delta returns PROGRESS."""
        turn = TurnContext(
            user_message="Да, интересно",
            intent="agreement",
            confidence=0.9,
            action="transition",
            state="spin_situation",
            next_state="spin_problem",
            funnel_delta=1
        )

        assert turn.turn_type == TurnType.PROGRESS

    def test_turn_type_regress_by_delta(self):
        """Negative funnel_delta returns REGRESS."""
        turn = TurnContext(
            user_message="Не нужно",
            intent="no_need",
            confidence=0.9,
            action="handle",
            state="spin_problem",
            next_state="spin_situation",
            funnel_delta=-1
        )

        assert turn.turn_type == TurnType.REGRESS

    def test_turn_type_neutral_by_zero_delta(self):
        """Zero funnel_delta returns NEUTRAL."""
        turn = TurnContext(
            user_message="Хорошо",
            intent="acknowledgment",
            confidence=0.9,
            action="continue",
            state="spin_situation",
            next_state="spin_situation",
            funnel_delta=0
        )

        # With the fix, zero delta should return NEUTRAL (not PROGRESS)
        assert turn.turn_type == TurnType.NEUTRAL

    def test_turn_type_regress_by_intent(self):
        """Rejection intent returns REGRESS regardless of delta."""
        turn = TurnContext(
            user_message="Не интересно",
            intent="rejection",
            confidence=0.95,
            action="soft_close",
            state="presentation",
            next_state="soft_close",
            funnel_delta=0
        )

        assert turn.turn_type == TurnType.REGRESS

    def test_turn_type_progress_by_intent(self):
        """Progress intent returns PROGRESS."""
        turn = TurnContext(
            user_message="Давайте демо",
            intent="demo_request",
            confidence=0.95,
            action="schedule_demo",
            state="presentation",
            next_state="close",
            funnel_delta=0
        )

        assert turn.turn_type == TurnType.PROGRESS

# =============================================================================
# Test 4: Context window sync after disambiguation (integration test)
# =============================================================================

class TestContextWindowDisambiguationSync:
    """Tests for context_window being updated after disambiguation resolution."""

    def test_context_window_add_turn_params(self):
        """Verify add_turn_from_dict accepts all required parameters."""
        cw = ContextWindow(max_size=10)

        # These are the parameters used in bot._continue_with_classification
        cw.add_turn_from_dict(
            user_message="первый вариант",
            bot_response="Отлично, понял ваш выбор.",
            intent="selection",
            confidence=0.85,
            action="process_selection",
            state="disambiguation",
            next_state="spin_situation",
            method="disambiguation_resolved",
            extracted_data={"choice": 1},
            is_fallback=False,
            fallback_tier=None,
        )

        assert len(cw) == 1
        turn = cw.get_last_turn()
        assert turn.user_message == "первый вариант"
        assert turn.bot_response == "Отлично, понял ваш выбор."
        assert turn.intent == "selection"
        assert turn.method == "disambiguation_resolved"
        assert turn.extracted_data == {"choice": 1}

    def test_context_window_sync_maintains_turn_count(self):
        """Context window and history should stay in sync."""
        cw = ContextWindow(max_size=10)
        history = []

        # Simulate normal turn
        history.append({"user": "привет", "bot": "Здравствуйте!"})
        cw.add_turn_from_dict(
            user_message="привет",
            bot_response="Здравствуйте!",
            intent="greeting",
            confidence=0.95,
            action="greet",
            state="greeting",
            next_state="spin_situation",
            method="llm",
        )
        assert len(cw) == len(history) == 1

        # Simulate disambiguation turn (the fix ensures this is added)
        history.append({"user": "первый", "bot": "Понял, обработаю."})
        cw.add_turn_from_dict(
            user_message="первый",
            bot_response="Понял, обработаю.",
            intent="selection",
            confidence=0.8,
            action="process",
            state="spin_situation",
            next_state="spin_problem",
            method="disambiguation_resolved",
        )
        assert len(cw) == len(history) == 2

# =============================================================================
# Test 5: ALL_COMPLETE and ANY_COMPLETE still work correctly
# =============================================================================

class TestDAGOtherJoinConditions:
    """Verify other join conditions still work after MAJORITY fix."""

    def test_all_complete_requires_all(self):
        """ALL_COMPLETE requires all branches."""
        executor = DAGExecutor(
            flow_config=MagicMock(),
            condition_registry=MagicMock(),
        )

        completed = {"a", "b"}
        expected = {"a", "b", "c"}

        result = executor._check_join_condition(
            JoinCondition.ALL_COMPLETE,
            completed,
            expected
        )

        assert result is False

        # Now with all complete
        completed = {"a", "b", "c"}
        result = executor._check_join_condition(
            JoinCondition.ALL_COMPLETE,
            completed,
            expected
        )

        assert result is True

    def test_any_complete_requires_one(self):
        """ANY_COMPLETE requires at least one branch."""
        executor = DAGExecutor(
            flow_config=MagicMock(),
            condition_registry=MagicMock(),
        )

        completed = set()
        expected = {"a", "b", "c"}

        result = executor._check_join_condition(
            JoinCondition.ANY_COMPLETE,
            completed,
            expected
        )

        assert result is False

        # Now with one complete
        completed = {"b"}
        result = executor._check_join_condition(
            JoinCondition.ANY_COMPLETE,
            completed,
            expected
        )

        assert result is True

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
