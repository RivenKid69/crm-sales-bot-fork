"""
RuleResolver - разрешение rules и transitions через условия.

Поддерживает форматы правил:
- Simple: "action" (строка)
- Conditional dict: {"when": "condition_name", "then": "action"}
- Conditional list: [{...}, {...}, "default"] - цепочка условий

Part of Phase 3: IntentTracker + RuleResolver (ARCHITECTURE_UNIFIED_PLAN.md)
"""

from typing import Dict, List, Optional, Any, Union, Set, Iterator
from dataclasses import dataclass, field

from src.conditions.registry import ConditionRegistry, ConditionNotFoundError
from src.conditions.trace import EvaluationTrace, Resolution


# Type aliases for rule formats
SimpleRule = str
ConditionalRule = Dict[str, str]  # {"when": "condition", "then": "action"}
RuleChain = List[Union[ConditionalRule, str, None]]  # [{...}, {...}, "default"] or [..., None]
RuleValue = Union[SimpleRule, ConditionalRule, RuleChain]


class UnknownConditionError(Exception):
    """Raised when a rule references an unknown condition."""

    def __init__(self, condition_name: str, rule_name: str, state: str = ""):
        self.condition_name = condition_name
        self.rule_name = rule_name
        self.state = state
        message = f"Unknown condition '{condition_name}' in rule '{rule_name}'"
        if state:
            message += f" (state: {state})"
        super().__init__(message)


class UnknownTargetStateError(Exception):
    """Raised when a transition references an unknown target state."""

    def __init__(self, target_state: str, rule_name: str, state: str = ""):
        self.target_state = target_state
        self.rule_name = rule_name
        self.state = state
        message = f"Unknown target state '{target_state}' in rule '{rule_name}'"
        if state:
            message += f" (from state: {state})"
        super().__init__(message)


class InvalidRuleFormatError(Exception):
    """Raised when a rule has an invalid format."""

    def __init__(self, rule_name: str, reason: str, state: str = ""):
        self.rule_name = rule_name
        self.reason = reason
        self.state = state
        message = f"Invalid rule format for '{rule_name}': {reason}"
        if state:
            message += f" (state: {state})"
        super().__init__(message)


@dataclass
class ValidationError:
    """Single validation error."""
    error_type: str
    message: str
    state: str = ""
    rule_name: str = ""
    condition_name: str = ""
    target_state: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.error_type,
            "message": self.message,
            "state": self.state,
            "rule": self.rule_name,
            "condition": self.condition_name,
            "target": self.target_state
        }


@dataclass
class ValidationResult:
    """
    Result of config validation.

    Attributes:
        errors: List of validation errors
        warnings: List of validation warnings
        checked_rules: Number of rules checked
        checked_transitions: Number of transitions checked
    """
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)
    checked_rules: int = 0
    checked_transitions: int = 0

    @property
    def is_valid(self) -> bool:
        """Check if validation passed (no errors)."""
        return len(self.errors) == 0

    def add_error(
        self,
        error_type: str,
        message: str,
        state: str = "",
        rule_name: str = "",
        condition_name: str = "",
        target_state: str = ""
    ) -> None:
        """Add a validation error."""
        self.errors.append(ValidationError(
            error_type=error_type,
            message=message,
            state=state,
            rule_name=rule_name,
            condition_name=condition_name,
            target_state=target_state
        ))

    def add_warning(
        self,
        error_type: str,
        message: str,
        state: str = "",
        rule_name: str = "",
        condition_name: str = "",
        target_state: str = ""
    ) -> None:
        """Add a validation warning."""
        self.warnings.append(ValidationError(
            error_type=error_type,
            message=message,
            state=state,
            rule_name=rule_name,
            condition_name=condition_name,
            target_state=target_state
        ))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "is_valid": self.is_valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "checked_rules": self.checked_rules,
            "checked_transitions": self.checked_transitions
        }


@dataclass
class RuleResult:
    """
    Result of rule resolution.

    Attributes:
        action: The resolved action (for rules)
        next_state: The resolved next state (for transitions), None = stay
        trace: Optional evaluation trace for debugging
    """
    action: str
    next_state: Optional[str] = None
    trace: Optional[EvaluationTrace] = None

    def __iter__(self) -> Iterator[Any]:
        """
        Support tuple unpacking for backward compatibility.

        Allows: action, state = resolver.resolve(...)
        """
        yield self.action
        yield self.next_state

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "action": self.action,
            "next_state": self.next_state,
        }
        if self.trace:
            result["trace"] = self.trace.to_dict()
        return result


class RuleResolver:
    """
    Resolves rules and transitions through conditions.

    Supports:
    - Simple rules (string)
    - Conditional rules (dict with "when"/"then")
    - Rule chains (list with conditions and default)
    - Optional tracing for debugging

    Example:
        resolver = RuleResolver(registry)

        # Simple rule
        action = resolver.resolve_action(
            intent="greeting",
            state_rules={"greeting": "greet_back"},
            global_rules={},
            ctx=context
        )

        # Conditional rule
        action = resolver.resolve_action(
            intent="price_question",
            state_rules={
                "price_question": [
                    {"when": "has_pricing_data", "then": "answer_with_facts"},
                    "deflect_and_continue"
                ]
            },
            global_rules={},
            ctx=context
        )
    """

    # Default fallback action when no rule matches
    DEFAULT_ACTION = "continue_current_goal"

    def __init__(
        self,
        registry: ConditionRegistry,
        default_action: str = None
    ):
        """
        Initialize resolver.

        Args:
            registry: Condition registry to use for evaluation
            default_action: Default action when no rule matches
        """
        self.registry = registry
        self.default_action = default_action or self.DEFAULT_ACTION

    def resolve_action(
        self,
        intent: str,
        state_rules: Dict[str, RuleValue],
        global_rules: Dict[str, RuleValue],
        ctx: Any,
        state: str = "",
        trace: Optional[EvaluationTrace] = None
    ) -> str:
        """
        Resolve action for an intent.

        Resolution order:
        1. state_rules[intent]
        2. global_rules[intent]
        3. default_action

        Args:
            intent: Intent to resolve
            state_rules: Rules specific to current state
            global_rules: Global rules (fallback)
            ctx: Context for condition evaluation
            state: Current state name (for tracing)
            trace: Optional trace for debugging

        Returns:
            Resolved action string
        """
        # Try state rules first
        if intent in state_rules:
            result = self._evaluate_rule(
                rule=state_rules[intent],
                rule_name=intent,
                ctx=ctx,
                trace=trace
            )
            if result is not None:
                return result

        # Try global rules
        if intent in global_rules:
            result = self._evaluate_rule(
                rule=global_rules[intent],
                rule_name=intent,
                ctx=ctx,
                trace=trace
            )
            if result is not None:
                return result

        # Fallback to default
        if trace:
            trace.set_result(self.default_action, Resolution.FALLBACK)

        return self.default_action

    def resolve_transition(
        self,
        intent: str,
        transitions: Dict[str, RuleValue],
        ctx: Any,
        state: str = "",
        trace: Optional[EvaluationTrace] = None
    ) -> Optional[str]:
        """
        Resolve next state for an intent.

        Args:
            intent: Intent to resolve
            transitions: Transition rules
            ctx: Context for condition evaluation
            state: Current state name (for tracing)
            trace: Optional trace for debugging

        Returns:
            Next state name, or None to stay in current state
        """
        if intent not in transitions:
            if trace:
                trace.set_result("(stay)", Resolution.NONE)
            return None

        result = self._evaluate_rule(
            rule=transitions[intent],
            rule_name=intent,
            ctx=ctx,
            trace=trace
        )

        return result

    def _evaluate_rule(
        self,
        rule: RuleValue,
        rule_name: str,
        ctx: Any,
        trace: Optional[EvaluationTrace] = None
    ) -> Optional[str]:
        """
        Evaluate a single rule.

        Handles all rule formats:
        - Simple string: return as-is
        - Conditional dict: evaluate condition, return "then" if True
        - Rule chain (list): evaluate each condition in order

        Args:
            rule: The rule to evaluate
            rule_name: Name of the rule (for tracing)
            ctx: Context for condition evaluation
            trace: Optional trace for debugging

        Returns:
            Resolved action/state, or None if no match
        """
        # Simple string rule
        if isinstance(rule, str):
            if trace:
                trace.set_result(rule, Resolution.SIMPLE)
            return rule

        # None - explicit "stay in current state"
        if rule is None:
            if trace:
                trace.set_result("(stay)", Resolution.NONE)
            return None

        # Conditional dict: {"when": "condition", "then": "action"}
        if isinstance(rule, dict):
            return self._evaluate_conditional_rule(rule, rule_name, ctx, trace)

        # Rule chain (list)
        if isinstance(rule, list):
            return self._evaluate_rule_chain(rule, rule_name, ctx, trace)

        # Unknown format
        raise InvalidRuleFormatError(
            rule_name,
            f"unexpected type {type(rule).__name__}"
        )

    def _evaluate_conditional_rule(
        self,
        rule: ConditionalRule,
        rule_name: str,
        ctx: Any,
        trace: Optional[EvaluationTrace] = None
    ) -> Optional[str]:
        """
        Evaluate a conditional rule dict.

        Format: {"when": "condition_name", "then": "action"}

        Args:
            rule: The conditional rule dict
            rule_name: Name of the rule
            ctx: Context for evaluation
            trace: Optional trace

        Returns:
            Action if condition is True, None otherwise
        """
        if "when" not in rule or "then" not in rule:
            raise InvalidRuleFormatError(
                rule_name,
                "conditional rule must have 'when' and 'then' keys"
            )

        condition_name = rule["when"]
        action = rule["then"]

        # Evaluate condition
        try:
            result = self.registry.evaluate(condition_name, ctx, trace)
        except ConditionNotFoundError:
            raise UnknownConditionError(condition_name, rule_name)

        if result:
            if trace:
                trace.set_result(action, Resolution.CONDITION_MATCHED, condition_name)
            return action

        return None

    def _evaluate_rule_chain(
        self,
        chain: RuleChain,
        rule_name: str,
        ctx: Any,
        trace: Optional[EvaluationTrace] = None
    ) -> Optional[str]:
        """
        Evaluate a rule chain (list of conditions with default).

        Format: [{"when": "cond1", "then": "act1"}, {"when": "cond2", "then": "act2"}, "default"]

        The last element can be:
        - String: default action
        - None: stay in current state
        - Dict: another conditional rule

        Args:
            chain: List of conditional rules with optional default
            rule_name: Name of the rule
            ctx: Context for evaluation
            trace: Optional trace

        Returns:
            First matching action, default, or None
        """
        if not chain:
            raise InvalidRuleFormatError(rule_name, "empty rule chain")

        default_value: Optional[str] = None
        has_default = False

        for i, item in enumerate(chain):
            # Check if this is the default (last string or None)
            if isinstance(item, str) and i == len(chain) - 1:
                default_value = item
                has_default = True
                continue
            if item is None and i == len(chain) - 1:
                default_value = None
                has_default = True
                continue

            # Evaluate conditional rule
            if isinstance(item, dict):
                result = self._evaluate_conditional_rule(item, rule_name, ctx, trace)
                if result is not None:
                    return result
            elif isinstance(item, str):
                # String in middle of chain - treat as simple rule
                if trace:
                    trace.set_result(item, Resolution.SIMPLE)
                return item
            elif item is None:
                # None in middle - stay
                if trace:
                    trace.set_result("(stay)", Resolution.NONE)
                return None

        # Return default if we have one
        if has_default:
            if trace:
                trace.set_result(
                    default_value or "(stay)",
                    Resolution.DEFAULT
                )
            return default_value

        # No match and no default
        return None

    def validate_config(
        self,
        states_config: Dict[str, Dict[str, Any]],
        global_rules: Dict[str, RuleValue] = None,
        known_states: Set[str] = None
    ) -> ValidationResult:
        """
        Validate rules configuration.

        Checks for:
        - Unknown conditions in rules
        - Unknown target states in transitions
        - Invalid rule formats

        Args:
            states_config: SALES_STATES configuration
            global_rules: Global rules dict (optional)
            known_states: Set of valid state names (defaults to states_config keys)

        Returns:
            ValidationResult with errors and warnings
        """
        result = ValidationResult()

        # Determine known states
        if known_states is None:
            known_states = set(states_config.keys())

        # Get all registered conditions
        registered_conditions = set(self.registry.list_all())

        # Validate each state
        for state_name, state_config in states_config.items():
            # Validate rules
            rules = state_config.get("rules", {})
            for intent, rule in rules.items():
                result.checked_rules += 1
                self._validate_rule(
                    rule=rule,
                    rule_name=intent,
                    state=state_name,
                    registered_conditions=registered_conditions,
                    known_states=known_states,
                    result=result,
                    is_transition=False
                )

            # Validate transitions
            transitions = state_config.get("transitions", {})
            for intent, rule in transitions.items():
                result.checked_transitions += 1
                self._validate_rule(
                    rule=rule,
                    rule_name=intent,
                    state=state_name,
                    registered_conditions=registered_conditions,
                    known_states=known_states,
                    result=result,
                    is_transition=True
                )

        # Validate global rules
        if global_rules:
            for intent, rule in global_rules.items():
                result.checked_rules += 1
                self._validate_rule(
                    rule=rule,
                    rule_name=intent,
                    state="(global)",
                    registered_conditions=registered_conditions,
                    known_states=known_states,
                    result=result,
                    is_transition=False
                )

        return result

    def _validate_rule(
        self,
        rule: RuleValue,
        rule_name: str,
        state: str,
        registered_conditions: Set[str],
        known_states: Set[str],
        result: ValidationResult,
        is_transition: bool
    ) -> None:
        """
        Validate a single rule.

        Args:
            rule: The rule to validate
            rule_name: Name of the rule
            state: State this rule belongs to
            registered_conditions: Set of valid condition names
            known_states: Set of valid state names
            result: ValidationResult to add errors to
            is_transition: Whether this is a transition (validate target states)
        """
        # Simple string rule
        if isinstance(rule, str):
            if is_transition and rule not in known_states:
                result.add_error(
                    "unknown_target_state",
                    f"Unknown target state '{rule}'",
                    state=state,
                    rule_name=rule_name,
                    target_state=rule
                )
            return

        # None - valid for transitions
        if rule is None:
            return

        # Conditional dict
        if isinstance(rule, dict):
            self._validate_conditional_rule(
                rule, rule_name, state,
                registered_conditions, known_states,
                result, is_transition
            )
            return

        # Rule chain (list)
        if isinstance(rule, list):
            self._validate_rule_chain(
                rule, rule_name, state,
                registered_conditions, known_states,
                result, is_transition
            )
            return

        # Unknown format
        result.add_error(
            "invalid_format",
            f"Invalid rule format: {type(rule).__name__}",
            state=state,
            rule_name=rule_name
        )

    def _validate_conditional_rule(
        self,
        rule: ConditionalRule,
        rule_name: str,
        state: str,
        registered_conditions: Set[str],
        known_states: Set[str],
        result: ValidationResult,
        is_transition: bool
    ) -> None:
        """Validate a conditional rule dict."""
        # Check required keys
        if "when" not in rule:
            result.add_error(
                "missing_key",
                "Conditional rule missing 'when' key",
                state=state,
                rule_name=rule_name
            )
            return

        if "then" not in rule:
            result.add_error(
                "missing_key",
                "Conditional rule missing 'then' key",
                state=state,
                rule_name=rule_name
            )
            return

        # Check condition exists
        condition_name = rule["when"]
        if condition_name not in registered_conditions:
            result.add_error(
                "unknown_condition",
                f"Unknown condition '{condition_name}'",
                state=state,
                rule_name=rule_name,
                condition_name=condition_name
            )

        # Check target state for transitions
        if is_transition:
            target = rule["then"]
            if target not in known_states:
                result.add_error(
                    "unknown_target_state",
                    f"Unknown target state '{target}'",
                    state=state,
                    rule_name=rule_name,
                    target_state=target
                )

    def _validate_rule_chain(
        self,
        chain: RuleChain,
        rule_name: str,
        state: str,
        registered_conditions: Set[str],
        known_states: Set[str],
        result: ValidationResult,
        is_transition: bool
    ) -> None:
        """Validate a rule chain."""
        if not chain:
            result.add_error(
                "empty_chain",
                "Empty rule chain",
                state=state,
                rule_name=rule_name
            )
            return

        for i, item in enumerate(chain):
            if isinstance(item, dict):
                self._validate_conditional_rule(
                    item, rule_name, state,
                    registered_conditions, known_states,
                    result, is_transition
                )
            elif isinstance(item, str):
                # String - either simple rule or default
                if is_transition and item not in known_states:
                    result.add_error(
                        "unknown_target_state",
                        f"Unknown target state '{item}'",
                        state=state,
                        rule_name=rule_name,
                        target_state=item
                    )
            elif item is None:
                # None is valid (stay in state)
                pass
            else:
                result.add_error(
                    "invalid_chain_item",
                    f"Invalid item type in chain: {type(item).__name__}",
                    state=state,
                    rule_name=rule_name
                )


def create_resolver(registry: ConditionRegistry = None) -> RuleResolver:
    """
    Factory function to create RuleResolver.

    Args:
        registry: Optional registry (defaults to sm_registry)

    Returns:
        Configured RuleResolver
    """
    if registry is None:
        from src.conditions.state_machine.registry import sm_registry
        registry = sm_registry

    return RuleResolver(registry)


# Export all public components
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
