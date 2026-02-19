# src/blackboard/models.py

"""
Data models for Dialogue Blackboard System.

This module defines the core data structures:
- Proposal: A proposal made by a Knowledge Source
- ResolvedDecision: The final decision after conflict resolution
- ContextSnapshot: Immutable snapshot of dialogue context for Knowledge Sources
"""

from dataclasses import dataclass, field
from typing import Any, Optional, List, Dict, TYPE_CHECKING
from datetime import datetime

from .enums import Priority, ProposalType

if TYPE_CHECKING:
    from .protocols import TenantConfig, IIntentTrackerReader, IIntentTracker
    from src.context_envelope import ContextEnvelope


# =============================================================================
# FrozenDict — immutable dict subclass (Issue #4)
# =============================================================================

class FrozenDict(dict):
    """Immutable dict subclass that raises TypeError on any mutation.

    Unlike MappingProxyType, passes isinstance(x, dict) checks — zero breaking
    changes to existing code that uses isinstance for type dispatch on YAML configs.

    Read operations work normally: .get(), [], in, len, .items(), .keys(), .values()
    Mutation operations blocked: []= , del, .update(), .pop(), .clear(), .setdefault()
    dict(frozen) creates a mutable copy (standard Python dict constructor behavior).
    """
    _FROZEN_MSG = "FrozenDict does not support mutation"

    def __setitem__(self, key, value):
        raise TypeError(self._FROZEN_MSG)

    def __delitem__(self, key):
        raise TypeError(self._FROZEN_MSG)

    def update(self, *args, **kwargs):
        raise TypeError(self._FROZEN_MSG)

    def pop(self, *args):
        raise TypeError(self._FROZEN_MSG)

    def popitem(self):
        raise TypeError(self._FROZEN_MSG)

    def clear(self):
        raise TypeError(self._FROZEN_MSG)

    def setdefault(self, key, default=None):
        if key not in self:
            raise TypeError(self._FROZEN_MSG)
        return self[key]

    def __ior__(self, other):  # |= operator
        raise TypeError(self._FROZEN_MSG)

    def __repr__(self):
        return f"FrozenDict({dict.__repr__(self)})"


def deep_freeze_dict(d: dict) -> FrozenDict:
    """Recursively create immutable FrozenDict from dict.

    All nested dicts become FrozenDict. Lists are NOT frozen (accepted limitation).
    O(n) on creation, O(1) per access — negligible for config-sized dicts.
    Passes isinstance(x, dict) for all nested levels.
    """
    return FrozenDict({
        k: deep_freeze_dict(v) if isinstance(v, dict) and not isinstance(v, FrozenDict) else v
        for k, v in d.items()
    })


# =============================================================================
# GoBackInfo — frozen snapshot of CircularFlowManager state
# =============================================================================

@dataclass(frozen=True)
class GoBackInfo:
    """Read-only snapshot of CircularFlowManager state for GoBackGuardSource."""
    target_state: Optional[str]   # Pre-computed go_back target for current state
    limit_reached: bool
    remaining: int
    goback_count: int
    max_gobacks: int
    history: tuple = ()           # Frozen go_back history (tuple of tuples)


# =============================================================================
# IntentTrackerReadOnly — read-only proxy for ContextSnapshot
# =============================================================================

class IntentTrackerReadOnly:
    """Read-only proxy for IntentTracker in ContextSnapshot.

    Delegates all read methods to the live tracker.
    Does NOT expose record() or advance_turn().
    Any mutation attempt raises AttributeError.
    """
    __slots__ = ('_tracker',)

    def __init__(self, tracker: 'IIntentTracker'):
        object.__setattr__(self, '_tracker', tracker)

    def __setattr__(self, name, value):
        raise AttributeError("IntentTrackerReadOnly is immutable")

    @property
    def turn_number(self) -> int:
        return self._tracker.turn_number

    @property
    def prev_intent(self) -> Optional[str]:
        return self._tracker.prev_intent

    @property
    def last_intent(self) -> Optional[str]:
        return self._tracker.last_intent

    @property
    def last_state(self) -> Optional[str]:
        return self._tracker.last_state

    @property
    def history_length(self) -> int:
        return self._tracker.history_length

    def objection_consecutive(self) -> int:
        return self._tracker.objection_consecutive()

    def objection_total(self) -> int:
        return self._tracker.objection_total()

    def total_count(self, intent: str) -> int:
        return self._tracker.total_count(intent)

    def category_total(self, category: str) -> int:
        return self._tracker.category_total(category)

    def streak_count(self, intent: str) -> int:
        return self._tracker.streak_count(intent)

    def category_streak(self, category: str) -> int:
        return self._tracker.category_streak(category)

    def get_intents_by_category(self, category: str) -> list:
        return self._tracker.get_intents_by_category(category)

    def get_recent_intents(self, limit: int = 5) -> List[str]:
        return self._tracker.get_recent_intents(limit)


# =============================================================================
# 5.3 Proposal Dataclass
# =============================================================================

@dataclass
class Proposal:
    """
    A proposal made by a Knowledge Source.

    Attributes:
        type: Type of proposal (ACTION, TRANSITION)
        value: The proposed value (action name, state name, data dict, flag dict)
        priority: Priority level for conflict resolution
        source_name: Name of the Knowledge Source that made this proposal
        reason_code: Documented reason code for auditability
        combinable: Whether this action can coexist with transitions
                    Only applicable for ACTION type.
                    True = action can be merged with transitions
                    False = action blocks all transitions (e.g., rejection)
        metadata: Additional context about the proposal
        created_at: Timestamp when proposal was created
    """
    type: ProposalType
    value: Any
    priority: Priority
    source_name: str
    reason_code: str
    combinable: bool = True  # Default: actions can coexist with transitions
    metadata: dict = field(default_factory=dict)
    priority_rank: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.now)

    def validate(self) -> List[str]:
        """
        Validate the proposal.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Check priority is valid
        if not isinstance(self.priority, Priority):
            errors.append(f"Invalid priority: {self.priority}. Must be Priority enum.")

        # Check type is valid
        if not isinstance(self.type, ProposalType):
            errors.append(f"Invalid type: {self.type}. Must be ProposalType enum.")

        # Check value is not None
        if self.value is None:
            errors.append("Proposal value cannot be None.")

        # Check reason_code is not empty
        if not self.reason_code or not self.reason_code.strip():
            errors.append("Proposal must have a non-empty reason_code.")

        # Check source_name is not empty
        if not self.source_name or not self.source_name.strip():
            errors.append("Proposal must have a non-empty source_name.")

        # Type-specific validation
        if self.type == ProposalType.ACTION:
            if not isinstance(self.value, str):
                errors.append(f"ACTION value must be string, got {type(self.value)}")

        elif self.type == ProposalType.TRANSITION:
            if not isinstance(self.value, str):
                errors.append(f"TRANSITION value must be string, got {type(self.value)}")
            # combinable is not applicable for transitions
            if not self.combinable:
                errors.append("TRANSITION proposals cannot have combinable=False")

        return errors

    def __repr__(self):
        comb_str = f", combinable={self.combinable}" if self.type == ProposalType.ACTION else ""
        return (f"Proposal({self.type.name}, '{self.value}', {self.priority.name}, "
                f"source='{self.source_name}', reason='{self.reason_code}'{comb_str})")


# =============================================================================
# 5.4 ResolvedDecision Dataclass
# =============================================================================

@dataclass
class ResolvedDecision:
    """
    The final decision after conflict resolution.

    ВАЖНО: Этот класс должен обеспечивать полную совместимость с существующим
    интерфейсом state_machine.process() для бесшовной интеграции с bot.py.

    Attributes:
        action: The action to execute (e.g., "answer_with_pricing")
        next_state: The state to transition to (or current state if no transition)
        reason_codes: List of reason codes that contributed to this decision
        rejected_proposals: Proposals that were not selected (for debugging)
        resolution_trace: Detailed trace of the resolution process
        data_updates: Data fields to update in collected_data
        flags_to_set: Flags to set after transition

        # === COMPATIBILITY FIELDS (для совместимости с bot.py) ===
        prev_state: State before this decision (needed for metrics, state change detection)
        goal: Goal from state configuration (needed for generator context)
        collected_data: Full collected_data dict AFTER applying data_updates
        missing_data: List of missing required data fields
        optional_data: List of missing optional data fields
        is_final: Whether next_state is a final state
        spin_phase: Current phase (from state config)
        circular_flow: CircularFlowManager stats
        objection_flow: Objection tracking stats
    """
    # === CORE FIELDS ===
    action: str
    next_state: str
    reason_codes: List[str] = field(default_factory=list)
    rejected_proposals: List['Proposal'] = field(default_factory=list)
    resolution_trace: Dict[str, Any] = field(default_factory=dict)
    data_updates: Dict[str, Any] = field(default_factory=dict)
    flags_to_set: Dict[str, Any] = field(default_factory=dict)

    # === COMPATIBILITY FIELDS (заполняются Orchestrator'ом) ===
    prev_state: str = ""
    goal: str = ""
    collected_data: Dict[str, Any] = field(default_factory=dict)
    missing_data: List[str] = field(default_factory=list)
    optional_data: List[str] = field(default_factory=list)
    is_final: bool = False
    spin_phase: Optional[str] = None
    prev_phase: Optional[str] = None  # Phase before transition (for decision_trace)
    circular_flow: Dict[str, Any] = field(default_factory=dict)
    objection_flow: Dict[str, Any] = field(default_factory=dict)

    # Disambiguation metadata (filled by Orchestrator for ask_clarification path)
    disambiguation_options: List[Dict[str, Any]] = field(default_factory=list)
    disambiguation_question: str = ""

    # Terminal state requirements (filled by Orchestrator from YAML config).
    # Maps terminal state name → list of required collected_data fields.
    # Used by generator to build context-aware closing_data_request instructions.
    terminal_state_requirements: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization/logging."""
        return {
            "action": self.action,
            "next_state": self.next_state,
            "reason_codes": self.reason_codes,
            "rejected_proposals_count": len(self.rejected_proposals),
            "rejected_proposals": [str(p) for p in self.rejected_proposals],
            "resolution_trace": self.resolution_trace,
            "data_updates": self.data_updates,
            "flags_to_set": self.flags_to_set,
            # Compatibility fields
            "prev_state": self.prev_state,
            "goal": self.goal,
            "is_final": self.is_final,
            "spin_phase": self.spin_phase,
        }

    def to_sm_result(self) -> Dict[str, Any]:
        """
        Convert to legacy sm_result format for full compatibility with bot.py.

        КРИТИЧЕСКИ ВАЖНО: bot.py ожидает Dict с определёнными полями.
        DialoguePolicy модифицирует этот dict in-place.
        Generator использует goal, collected_data, missing_data, spin_phase.

        Returns:
            Dict в формате, идентичном state_machine.process() output
        """
        result = {
            # Core fields (from Blackboard)
            "action": self.action,
            "next_state": self.next_state,

            # Compatibility fields (заполнены Orchestrator'ом)
            "prev_state": self.prev_state,
            "goal": self.goal,
            "collected_data": self.collected_data,
            "missing_data": self.missing_data,
            "optional_data": self.optional_data,
            "is_final": self.is_final,
            "spin_phase": self.spin_phase,
            "prev_phase": self.prev_phase,  # For decision_trace phase tracking
            "circular_flow": self.circular_flow,
            "objection_flow": self.objection_flow,

            # New fields (Blackboard-specific, для улучшенной трассировки)
            "reason_codes": self.reason_codes,
            "resolution_trace": self.resolution_trace,
        }

        # Add trace field for decision_trace.py compatibility
        # (decision_trace.record_state_machine reads sm_result.get("trace"))
        if self.resolution_trace:
            result["trace"] = self.resolution_trace

        # Terminal state requirements — always include (empty dict is fine for non-closing states)
        if self.terminal_state_requirements:
            result["terminal_state_requirements"] = self.terminal_state_requirements

        # Disambiguation metadata (for bot.py ask_clarification response path)
        # NOTE: Intentional falsy check — empty list is NOT included in sm_result.
        # bot.py Defense Layer 2 handles the fallback if options are unexpectedly empty.
        if self.disambiguation_options:
            result["disambiguation_options"] = self.disambiguation_options
            result["disambiguation_question"] = self.disambiguation_question

        return result

    def __repr__(self):
        return (f"ResolvedDecision(action='{self.action}', next_state='{self.next_state}', "
                f"reasons={self.reason_codes}, rejected={len(self.rejected_proposals)})")


# =============================================================================
# 5.5 ContextSnapshot Dataclass
# =============================================================================

@dataclass(frozen=True)  # Immutable!
class ContextSnapshot:
    """
    Immutable snapshot of dialogue context for Knowledge Sources.

    This is the read-only view that Knowledge Sources use to make decisions.
    Sources cannot modify this directly - they can only propose changes.

    Attributes:
        state: Current dialogue state (e.g., "spin_situation")
        collected_data: All collected data fields (immutable copy)
        current_intent: The intent of the current user message
        intent_tracker: Reference to IntentTracker (for history queries)
        context_envelope: Full context envelope from Phase 5
        turn_number: Current turn number in the conversation
        persona: Detected user persona (for dynamic limits)
        state_config: Configuration for current state
        flow_config: Configuration for current flow
        tenant_id: Tenant identifier for multi-tenancy support
        tenant_config: Tenant-specific configuration (feature flags, limits)
    """
    state: str
    collected_data: Dict[str, Any]
    current_intent: str
    intent_tracker: 'IIntentTrackerReader'
    context_envelope: Optional['ContextEnvelope']
    turn_number: int
    persona: str
    state_config: Dict[str, Any]
    flow_config: Dict[str, Any]
    # FUNDAMENTAL FIX: state_to_phase mapping for custom flows (BANT, MEDDIC, etc.)
    # Built from FlowConfig.state_to_phase property
    state_to_phase: Dict[str, str] = field(default_factory=dict)
    # New fields for encapsulation (#5)
    state_before_objection: Optional[str] = None
    valid_states: frozenset = field(default_factory=frozenset)
    go_back_info: Optional['GoBackInfo'] = None
    # Multi-tenancy support (DESIGN_PRINCIPLES.md Section 6)
    tenant_id: str = "default"
    tenant_config: Optional['TenantConfig'] = None
    # Guard-class sources need raw message (loop detection) and frustration
    # (independent of context_envelope which may be None if feature flags off)
    user_message: str = ""
    frustration_level: int = 0

    # Computed properties for convenience
    @property
    def last_intent(self) -> Optional[str]:
        """Get the previous intent (before current)."""
        return self.intent_tracker.prev_intent

    @property
    def objection_consecutive(self) -> int:
        """Get consecutive objection count."""
        return self.intent_tracker.objection_consecutive()

    @property
    def objection_total(self) -> int:
        """Get total objection count."""
        return self.intent_tracker.objection_total()

    @property
    def required_data(self) -> List[str]:
        """Get required data fields for current state."""
        return self.state_config.get("required_data", [])

    @property
    def optional_data_fields(self) -> List[str]:
        """Get optional data fields for current state."""
        return self.state_config.get("optional_data", [])

    @property
    def current_phase(self) -> Optional[str]:
        """
        Get current phase name.

        Uses state_to_phase mapping which is the CANONICAL source of truth
        for state -> phase resolution. The mapping already includes:
        - Reverse mapping from phase_mapping
        - Explicit phases from state configs (higher priority)

        Note: We also check state_config.phase as a fallback for backwards
        compatibility with code that passes incomplete state_to_phase.
        """
        # Primary: use state_to_phase which contains complete mapping
        phase = self.state_to_phase.get(self.state)
        if phase:
            return phase

        # Fallback: check state_config.phase for backwards compatibility
        explicit_phase = self.state_config.get("phase") or self.state_config.get("spin_phase")
        if explicit_phase:
            return explicit_phase

        return None

    def get_missing_required_data(self) -> List[str]:
        """Get list of required fields that are not yet collected."""
        return [
            f for f in self.required_data
            if not self.collected_data.get(f)
        ]

    def has_all_required_data(self) -> bool:
        """Check if all required data has been collected."""
        return len(self.get_missing_required_data()) == 0

    def get_transition(self, trigger: str) -> Optional[str]:
        """Get transition target for a trigger."""
        transitions = self.state_config.get("transitions", {})
        return transitions.get(trigger)

    def get_rule(self, intent: str) -> Optional[Any]:
        """Get rule for an intent in current state."""
        rules = self.state_config.get("rules", {})
        return rules.get(intent)

    def get_persona_limit(self, persona: str, limit_type: str) -> Optional[int]:
        """
        Get persona-specific limit with tenant override support.

        Multi-tenancy: Tenant config can override global persona limits.

        TODO: Dead method — never called from src/. flow_config.get("persona_limits")
        would always return {} because FlowConfig dict doesn't contain persona_limits.
        Persona limits are loaded via bot._load_persona_limits() from LoadedConfig.constants.
        Remove after confirming no external callers depend on this.

        Args:
            persona: Persona name (e.g., "aggressive", "busy")
            limit_type: Limit type ("consecutive" or "total")

        Returns:
            Limit value or None if not configured
        """
        # Check tenant override first
        if self.tenant_config and self.tenant_config.persona_limits_override:
            tenant_limits = self.tenant_config.persona_limits_override.get(persona, {})
            if limit_type in tenant_limits:
                return tenant_limits[limit_type]

        # Fall back to global config (passed via flow_config.constants)
        global_limits = self.flow_config.get("persona_limits", {}).get(persona, {})
        return global_limits.get(limit_type)

    def is_tenant_feature_enabled(self, feature_name: str) -> bool:
        """
        Check if a feature is enabled for current tenant.

        Args:
            feature_name: Feature flag name

        Returns:
            True if feature is enabled, False otherwise
        """
        if self.tenant_config and self.tenant_config.features:
            return self.tenant_config.features.get(feature_name, True)
        return True  # Default: all features enabled
