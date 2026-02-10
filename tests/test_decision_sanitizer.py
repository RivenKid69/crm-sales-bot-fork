"""Unit tests for DecisionSanitizer."""

from src.blackboard.decision_sanitizer import (
    DecisionSanitizer,
    INVALID_NEXT_STATE_REASON,
)
from src.blackboard.models import ResolvedDecision


def test_sanitize_target_valid_state_passthrough():
    sanitizer = DecisionSanitizer()

    result = sanitizer.sanitize_target(
        requested_state="spin_problem",
        current_state="spin_situation",
        valid_states={"spin_situation", "spin_problem"},
        source="test.valid",
    )

    assert result.is_valid is True
    assert result.sanitized is False
    assert result.effective_state == "spin_problem"
    assert result.reason_code is None
    assert result.diagnostic["requested_state"] == "spin_problem"
    assert result.diagnostic["effective_state"] == "spin_problem"


def test_sanitize_target_invalid_state_is_fail_safe():
    sanitizer = DecisionSanitizer()

    result = sanitizer.sanitize_target(
        requested_state="ghost",
        current_state="spin_situation",
        valid_states={"spin_situation", "spin_problem"},
        source="test.invalid",
    )

    assert result.is_valid is False
    assert result.sanitized is True
    assert result.effective_state == "spin_situation"
    assert result.reason_code == INVALID_NEXT_STATE_REASON
    assert result.diagnostic["sanitized_reason"] == INVALID_NEXT_STATE_REASON


def test_sanitize_decision_is_side_effect_free():
    sanitizer = DecisionSanitizer()
    decision = ResolvedDecision(action="continue_current_goal", next_state="ghost")

    result = sanitizer.sanitize_decision(
        decision=decision,
        current_state="greeting",
        valid_states={"greeting", "spin_situation"},
        source="test.decision",
    )

    assert decision.next_state == "ghost"  # caller applies mutation explicitly
    assert result.sanitized is True
    assert result.effective_state == "greeting"
