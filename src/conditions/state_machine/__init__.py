"""
StateMachine Domain for Conditional Rules System.

This package provides conditions specifically for the StateMachine,
handling rules and transitions in the dialogue state machine.

Main components:
- EvaluatorContext: Context for evaluating SM conditions
- sm_registry: Registry of all SM conditions
- sm_condition: Decorator for registering conditions
- Condition functions: has_pricing_data, price_repeated_3x, etc.

Part of Phase 2: StateMachine Domain (ARCHITECTURE_UNIFIED_PLAN.md)

Example usage:
    from src.conditions.state_machine import (
        EvaluatorContext,
        sm_registry,
        has_pricing_data,
    )

    # Create context from state machine
    ctx = EvaluatorContext.from_state_machine(sm, "price_question", config)

    # Evaluate condition directly
    if has_pricing_data(ctx):
        action = "answer_with_facts"

    # Or evaluate through registry
    if sm_registry.evaluate("has_pricing_data", ctx):
        action = "answer_with_facts"
"""

from src.conditions.state_machine.context import (
    EvaluatorContext,
    SimpleIntentTracker,
    IntentTrackerProtocol,
    INTENT_CATEGORIES,
)

# Re-export SPIN constants from yaml_config for backward compatibility
from src.yaml_config.constants import (
    SPIN_PHASES,
    SPIN_STATES,
    SPIN_PROGRESS_INTENTS,
)

# Create SPIN_STATE_TO_PHASE mapping from SPIN_STATES (reverse mapping)
SPIN_STATE_TO_PHASE = {v: k for k, v in SPIN_STATES.items()}

from src.conditions.state_machine.registry import (
    sm_registry,
    sm_condition,
    get_sm_registry,
)

# Contact validation utilities
from src.conditions.state_machine.contact_validator import (
    ContactValidator,
    ContactType,
    ValidationResult,
    has_valid_contact,
    get_validated_contact,
    validate_contact_string,
)

# Import all conditions to register them
from src.conditions.state_machine.conditions import (
    # Data conditions
    has_pricing_data,
    has_contact_info,
    has_validated_contact,
    has_valid_email,
    has_valid_phone,
    has_company_size,
    has_pain_point,
    has_pain_and_company_size,
    has_competitor_mention,
    missing_required_data,
    has_all_required_data,
    has_high_interest,
    has_desired_outcome,
    # Intent conditions
    price_repeated_3x,
    price_repeated_2x,
    technical_question_repeated_2x,
    objection_limit_reached,
    objection_consecutive_3x,
    objection_total_5x,
    is_current_intent_objection,
    is_current_intent_positive,
    is_current_intent_question,
    is_spin_progress_intent,
    objection_loop_escape,
    # State conditions (generic)
    is_phase_state,
    in_phase,
    post_phase,
    # State conditions (legacy aliases)
    is_spin_state,
    in_spin_phase,
    post_spin_phase,
    # Phase-specific conditions
    in_situation_phase,
    in_problem_phase,
    in_implication_phase,
    in_need_payoff_phase,
    # State-specific conditions
    is_presentation_state,
    is_close_state,
    is_greeting_state,
    is_handle_objection_state,
    is_soft_close_state,
    is_success_state,
    is_terminal_state,
    # Turn conditions
    is_first_turn,
    is_early_conversation,
    is_late_conversation,
    is_extended_conversation,
    # Combined conditions
    can_answer_price,
    should_deflect_price,
    ready_for_presentation,
    ready_for_close,
    can_handle_with_roi,
    # Context-aware conditions (Phase 5)
    client_frustrated,
    client_very_frustrated,
    client_stuck,
    client_oscillating,
    momentum_positive,
    momentum_negative,
    momentum_strong_positive,
    momentum_strong_negative,
    engagement_high,
    engagement_low,
    has_repeated_question,
    repeated_price_question,
    confidence_declining,
    many_objections,
    breakthrough_detected,
    in_breakthrough_window,
    guard_intervened,
    needs_repair,
    should_be_careful,
    can_accelerate,
    should_answer_directly,
)


def create_test_context(**kwargs) -> EvaluatorContext:
    """
    Factory function to create a test context with defaults.

    This is a convenience wrapper around EvaluatorContext.create_test_context()
    for easier test setup.

    Args:
        **kwargs: Arguments to pass to create_test_context

    Returns:
        A new EvaluatorContext instance
    """
    return EvaluatorContext.create_test_context(**kwargs)


# Export all public components
__all__ = [
    # Context
    "EvaluatorContext",
    "SimpleIntentTracker",
    "IntentTrackerProtocol",
    "create_test_context",
    # Constants
    "INTENT_CATEGORIES",
    # SPIN constants (from yaml_config, re-exported for backward compatibility)
    "SPIN_PHASES",
    "SPIN_STATES",
    "SPIN_STATE_TO_PHASE",
    "SPIN_PROGRESS_INTENTS",
    # Registry
    "sm_registry",
    "sm_condition",
    "get_sm_registry",
    # Contact validation
    "ContactValidator",
    "ContactType",
    "ValidationResult",
    "has_valid_contact",
    "get_validated_contact",
    "validate_contact_string",
    # Data conditions
    "has_pricing_data",
    "has_contact_info",
    "has_validated_contact",
    "has_valid_email",
    "has_valid_phone",
    "has_company_size",
    "has_pain_point",
    "has_pain_and_company_size",
    "has_competitor_mention",
    "missing_required_data",
    "has_all_required_data",
    "has_high_interest",
    "has_desired_outcome",
    # Intent conditions
    "price_repeated_3x",
    "price_repeated_2x",
    "technical_question_repeated_2x",
    "objection_limit_reached",
    "objection_consecutive_3x",
    "objection_total_5x",
    "is_current_intent_objection",
    "is_current_intent_positive",
    "is_current_intent_question",
    "is_spin_progress_intent",
    "objection_loop_escape",
    # State conditions (generic)
    "is_phase_state",
    "in_phase",
    "post_phase",
    # State conditions (legacy)
    "is_spin_state",
    "in_spin_phase",
    "post_spin_phase",
    # Phase-specific conditions
    "in_situation_phase",
    "in_problem_phase",
    "in_implication_phase",
    "in_need_payoff_phase",
    # State-specific conditions
    "is_presentation_state",
    "is_close_state",
    "is_greeting_state",
    "is_handle_objection_state",
    "is_soft_close_state",
    "is_success_state",
    "is_terminal_state",
    # Turn conditions
    "is_first_turn",
    "is_early_conversation",
    "is_late_conversation",
    "is_extended_conversation",
    # Combined conditions
    "can_answer_price",
    "should_deflect_price",
    "ready_for_presentation",
    "ready_for_close",
    "can_handle_with_roi",
    # Context-aware conditions (Phase 5)
    "client_frustrated",
    "client_very_frustrated",
    "client_stuck",
    "client_oscillating",
    "momentum_positive",
    "momentum_negative",
    "momentum_strong_positive",
    "momentum_strong_negative",
    "engagement_high",
    "engagement_low",
    "has_repeated_question",
    "repeated_price_question",
    "confidence_declining",
    "many_objections",
    "breakthrough_detected",
    "in_breakthrough_window",
    "guard_intervened",
    "needs_repair",
    "should_be_careful",
    "can_accelerate",
    "should_answer_directly",
]
