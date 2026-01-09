"""
Rules module - Rule resolution for conditional rules system.

This module provides:
- RuleResolver: Resolves rules and transitions through conditions
- RuleResult: Result of rule resolution with trace
- Validation utilities for config validation

Part of Phase 3: IntentTracker + RuleResolver (ARCHITECTURE_UNIFIED_PLAN.md)
"""

from src.rules.resolver import (
    RuleResolver,
    RuleResult,
    ValidationResult,
    ValidationError,
    UnknownConditionError,
    UnknownTargetStateError,
    InvalidRuleFormatError,
    create_resolver,
    RuleValue,
    SimpleRule,
    ConditionalRule,
    RuleChain,
)


__all__ = [
    "RuleResolver",
    "RuleResult",
    "ValidationResult",
    "ValidationError",
    "UnknownConditionError",
    "UnknownTargetStateError",
    "InvalidRuleFormatError",
    "create_resolver",
    "RuleValue",
    "SimpleRule",
    "ConditionalRule",
    "RuleChain",
]
