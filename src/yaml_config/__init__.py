"""
Configuration Module.

Provides centralized access to YAML-based configuration.

Usage:
    from src.config import (
        # Constants
        SPIN_PHASES, SPIN_STATES, OBJECTION_INTENTS,
        # Config loader
        get_config, init_config,
    )
"""

# Re-export constants for easy access
from src.yaml_config.constants import (
    # SPIN
    SPIN_PHASES,
    SPIN_STATES,
    SPIN_PROGRESS_INTENTS,
    # Limits
    MAX_CONSECUTIVE_OBJECTIONS,
    MAX_TOTAL_OBJECTIONS,
    MAX_GOBACKS,
    # Intent categories
    GO_BACK_INTENTS,
    OBJECTION_INTENTS,
    POSITIVE_INTENTS,
    QUESTION_INTENTS,
    SPIN_PROGRESS_INTENT_LIST,
    NEGATIVE_INTENTS,
    INTENT_CATEGORIES,
    # Policy
    OVERLAY_ALLOWED_STATES,
    PROTECTED_STATES,
    AGGRESSIVE_ACTIONS,
    REPAIR_ACTIONS,
    OBJECTION_ESCALATION_ACTIONS,
    # Lead scoring
    LEAD_SCORING_POSITIVE_WEIGHTS,
    LEAD_SCORING_NEGATIVE_WEIGHTS,
    LEAD_TEMPERATURE_THRESHOLDS,
    SKIP_PHASES_BY_TEMPERATURE,
    # Guard
    GUARD_CONFIG,
    GUARD_PROFILES,
    # Frustration
    MAX_FRUSTRATION,
    FRUSTRATION_WEIGHTS,
    FRUSTRATION_DECAY,
    FRUSTRATION_THRESHOLDS,
    # Circular flow
    ALLOWED_GOBACKS,
)

# Re-export config loader
from src.config_loader import (
    ConfigLoader,
    LoadedConfig,
    ConfigLoadError,
    ConfigValidationError,
    get_config,
    get_config_validated,
    init_config,
    validate_config_conditions,
)


__all__ = [
    # Constants
    "SPIN_PHASES",
    "SPIN_STATES",
    "SPIN_PROGRESS_INTENTS",
    "MAX_CONSECUTIVE_OBJECTIONS",
    "MAX_TOTAL_OBJECTIONS",
    "MAX_GOBACKS",
    "GO_BACK_INTENTS",
    "OBJECTION_INTENTS",
    "POSITIVE_INTENTS",
    "QUESTION_INTENTS",
    "SPIN_PROGRESS_INTENT_LIST",
    "NEGATIVE_INTENTS",
    "INTENT_CATEGORIES",
    "OVERLAY_ALLOWED_STATES",
    "PROTECTED_STATES",
    "AGGRESSIVE_ACTIONS",
    "REPAIR_ACTIONS",
    "OBJECTION_ESCALATION_ACTIONS",
    "LEAD_SCORING_POSITIVE_WEIGHTS",
    "LEAD_SCORING_NEGATIVE_WEIGHTS",
    "LEAD_TEMPERATURE_THRESHOLDS",
    "SKIP_PHASES_BY_TEMPERATURE",
    "GUARD_CONFIG",
    "GUARD_PROFILES",
    "MAX_FRUSTRATION",
    "FRUSTRATION_WEIGHTS",
    "FRUSTRATION_DECAY",
    "FRUSTRATION_THRESHOLDS",
    "ALLOWED_GOBACKS",
    # Config loader
    "ConfigLoader",
    "LoadedConfig",
    "ConfigLoadError",
    "ConfigValidationError",
    "get_config",
    "get_config_validated",
    "init_config",
    "validate_config_conditions",
]
