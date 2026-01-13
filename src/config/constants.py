"""
Centralized Constants Module.

This module provides a single source of truth for all constants
by loading them from YAML configuration files.

Usage:
    from src.config.constants import (
        SPIN_PHASES, SPIN_STATES, OBJECTION_INTENTS,
        POSITIVE_INTENTS, QUESTION_INTENTS, GO_BACK_INTENTS,
        MAX_CONSECUTIVE_OBJECTIONS, MAX_TOTAL_OBJECTIONS, MAX_GOBACKS,
        # DialoguePolicy constants
        OVERLAY_ALLOWED_STATES, PROTECTED_STATES, AGGRESSIVE_ACTIONS,
        # Lead scoring
        LEAD_SCORING_WEIGHTS, LEAD_TEMPERATURE_THRESHOLDS, SKIP_PHASES,
        # Guard
        GUARD_CONFIG,
        # Frustration
        FRUSTRATION_WEIGHTS, FRUSTRATION_THRESHOLDS,
    )

Part of Phase 1: State Machine Parameterization
"""

from typing import Dict, List, Set, Any, Tuple
from pathlib import Path
import yaml
import logging

logger = logging.getLogger(__name__)


def _load_yaml(file_path: Path) -> Dict[str, Any]:
    """Load YAML file safely."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning(f"Failed to load {file_path}: {e}")
        return {}


# Load YAML files
_config_dir = Path(__file__).parent
_constants = _load_yaml(_config_dir / "constants.yaml")


# =============================================================================
# SPIN CONFIGURATION
# =============================================================================

SPIN_PHASES: List[str] = _constants.get("spin", {}).get("phases", [
    "situation", "problem", "implication", "need_payoff"
])

SPIN_STATES: Dict[str, str] = _constants.get("spin", {}).get("states", {
    "situation": "spin_situation",
    "problem": "spin_problem",
    "implication": "spin_implication",
    "need_payoff": "spin_need_payoff",
})

SPIN_PROGRESS_INTENTS: Dict[str, str] = _constants.get("spin", {}).get("progress_intents", {
    "situation_provided": "situation",
    "problem_revealed": "problem",
    "implication_acknowledged": "implication",
    "need_expressed": "need_payoff",
})


# =============================================================================
# LIMITS
# =============================================================================

_limits = _constants.get("limits", {})

MAX_CONSECUTIVE_OBJECTIONS: int = _limits.get("max_consecutive_objections", 3)
MAX_TOTAL_OBJECTIONS: int = _limits.get("max_total_objections", 5)
MAX_GOBACKS: int = _limits.get("max_gobacks", 2)


# =============================================================================
# INTENT CATEGORIES
# =============================================================================

_intents = _constants.get("intents", {})
_categories = _intents.get("categories", {})

GO_BACK_INTENTS: List[str] = _intents.get("go_back", ["go_back", "correct_info"])

OBJECTION_INTENTS: List[str] = _categories.get("objection", [
    "objection_price",
    "objection_competitor",
    "objection_no_time",
    "objection_think",
])

POSITIVE_INTENTS: Set[str] = set(_categories.get("positive", [
    "agreement", "demo_request", "callback_request", "contact_provided",
    "consultation_request", "situation_provided", "problem_revealed",
    "implication_acknowledged", "need_expressed", "info_provided",
    "question_features", "question_integrations", "comparison",
    "greeting", "gratitude",
]))

QUESTION_INTENTS: List[str] = _categories.get("question", [
    "price_question", "pricing_details", "question_features",
    "question_integrations", "question_technical", "comparison",
])

SPIN_PROGRESS_INTENT_LIST: List[str] = _categories.get("spin_progress", [
    "situation_provided", "problem_revealed",
    "implication_acknowledged", "need_expressed",
])

NEGATIVE_INTENTS: List[str] = _categories.get("negative", [
    "rejection", "farewell",
    "objection_price", "objection_competitor",
    "objection_no_time", "objection_think",
])

# Full intent categories dict (for IntentTracker compatibility)
INTENT_CATEGORIES: Dict[str, List[str]] = {
    "objection": OBJECTION_INTENTS,
    "positive": list(POSITIVE_INTENTS),
    "question": QUESTION_INTENTS,
    "spin_progress": SPIN_PROGRESS_INTENT_LIST,
    "negative": NEGATIVE_INTENTS,
}


# =============================================================================
# DIALOGUE POLICY SETTINGS
# =============================================================================

_policy = _constants.get("policy", {})

OVERLAY_ALLOWED_STATES: Set[str] = set(_policy.get("overlay_allowed_states", [
    "spin_situation", "spin_problem", "spin_implication",
    "spin_need_payoff", "presentation", "handle_objection",
]))

PROTECTED_STATES: Set[str] = set(_policy.get("protected_states", [
    "greeting", "close", "success", "soft_close",
]))

AGGRESSIVE_ACTIONS: Set[str] = set(_policy.get("aggressive_actions", [
    "transition_to_presentation", "transition_to_close",
    "ask_for_demo", "ask_for_contact",
]))

REPAIR_ACTIONS: Dict[str, str] = _policy.get("repair_actions", {
    "stuck": "clarify_one_question",
    "oscillation": "summarize_and_clarify",
    "repeated_question": "answer_with_summary",
})

OBJECTION_ESCALATION_ACTIONS: Dict[str, str] = _policy.get("objection_actions", {
    "reframe": "reframe_value",
    "escalate": "handle_repeated_objection",
    "empathize": "empathize_and_redirect",
})


# =============================================================================
# LEAD SCORING SETTINGS
# =============================================================================

_lead_scoring = _constants.get("lead_scoring", {})

LEAD_SCORING_POSITIVE_WEIGHTS: Dict[str, int] = _lead_scoring.get("positive_weights", {
    "demo_request": 30, "contact_provided": 35, "callback_request": 25,
})

LEAD_SCORING_NEGATIVE_WEIGHTS: Dict[str, int] = _lead_scoring.get("negative_weights", {
    "objection_price": -15, "objection_no_time": -20, "rejection_soft": -25,
})

_thresholds = _lead_scoring.get("thresholds", {})
LEAD_TEMPERATURE_THRESHOLDS: Dict[str, Tuple[int, int]] = {
    "cold": tuple(_thresholds.get("cold", [0, 29])),
    "warm": tuple(_thresholds.get("warm", [30, 49])),
    "hot": tuple(_thresholds.get("hot", [50, 69])),
    "very_hot": tuple(_thresholds.get("very_hot", [70, 100])),
}

SKIP_PHASES_BY_TEMPERATURE: Dict[str, List[str]] = _lead_scoring.get("skip_phases", {
    "cold": [],
    "warm": ["spin_implication", "spin_need_payoff"],
    "hot": ["spin_problem", "spin_implication", "spin_need_payoff"],
    "very_hot": ["spin_situation", "spin_problem", "spin_implication", "spin_need_payoff"],
})


# =============================================================================
# CONVERSATION GUARD SETTINGS
# =============================================================================

_guard = _constants.get("guard", {})

GUARD_CONFIG: Dict[str, Any] = {
    "max_turns": _guard.get("max_turns", 25),
    "max_phase_attempts": _guard.get("max_phase_attempts", 3),
    "max_same_state": _guard.get("max_same_state", 4),
    "max_same_message": _guard.get("max_same_message", 2),
    "timeout_seconds": _guard.get("timeout_seconds", 1800),
    "progress_check_interval": _guard.get("progress_check_interval", 5),
    "min_unique_states_for_progress": _guard.get("min_unique_states_for_progress", 2),
    "high_frustration_threshold": _guard.get("high_frustration_threshold", 7),
}

GUARD_PROFILES: Dict[str, Dict[str, Any]] = _guard.get("profiles", {})


# =============================================================================
# FRUSTRATION TRACKER SETTINGS
# =============================================================================

_frustration = _constants.get("frustration", {})

MAX_FRUSTRATION: int = _frustration.get("max_level", 10)

FRUSTRATION_WEIGHTS: Dict[str, int] = _frustration.get("weights", {
    "frustrated": 3, "skeptical": 1, "rushed": 1, "confused": 1,
})

FRUSTRATION_DECAY: Dict[str, int] = _frustration.get("decay", {
    "neutral": 1, "positive": 2, "interested": 2,
})

FRUSTRATION_THRESHOLDS: Dict[str, int] = _frustration.get("thresholds", {
    "warning": 4, "high": 7, "critical": 9,
})


# =============================================================================
# CIRCULAR FLOW SETTINGS
# =============================================================================

_circular_flow = _constants.get("circular_flow", {})

ALLOWED_GOBACKS: Dict[str, str] = _circular_flow.get("allowed_gobacks", {
    "spin_problem": "spin_situation",
    "spin_implication": "spin_problem",
    "spin_need_payoff": "spin_implication",
    "presentation": "spin_need_payoff",
    "close": "presentation",
    "handle_objection": "presentation",
    "soft_close": "greeting",
})


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # SPIN
    "SPIN_PHASES",
    "SPIN_STATES",
    "SPIN_PROGRESS_INTENTS",
    # Limits
    "MAX_CONSECUTIVE_OBJECTIONS",
    "MAX_TOTAL_OBJECTIONS",
    "MAX_GOBACKS",
    # Intent categories
    "GO_BACK_INTENTS",
    "OBJECTION_INTENTS",
    "POSITIVE_INTENTS",
    "QUESTION_INTENTS",
    "SPIN_PROGRESS_INTENT_LIST",
    "NEGATIVE_INTENTS",
    "INTENT_CATEGORIES",
    # Policy
    "OVERLAY_ALLOWED_STATES",
    "PROTECTED_STATES",
    "AGGRESSIVE_ACTIONS",
    "REPAIR_ACTIONS",
    "OBJECTION_ESCALATION_ACTIONS",
    # Lead scoring
    "LEAD_SCORING_POSITIVE_WEIGHTS",
    "LEAD_SCORING_NEGATIVE_WEIGHTS",
    "LEAD_TEMPERATURE_THRESHOLDS",
    "SKIP_PHASES_BY_TEMPERATURE",
    # Guard
    "GUARD_CONFIG",
    "GUARD_PROFILES",
    # Frustration
    "MAX_FRUSTRATION",
    "FRUSTRATION_WEIGHTS",
    "FRUSTRATION_DECAY",
    "FRUSTRATION_THRESHOLDS",
    # Circular flow
    "ALLOWED_GOBACKS",
]
