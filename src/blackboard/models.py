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
    from .protocols import TenantConfig
    from src.intent_tracker import IntentTracker
    from src.context_envelope import ContextEnvelope


# =============================================================================
# 5.3 Proposal Dataclass
# =============================================================================

@dataclass
class Proposal:
    """
    A proposal made by a Knowledge Source.

    Attributes:
        type: Type of proposal (ACTION, TRANSITION, DATA_UPDATE, FLAG_SET)
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

        elif self.type == ProposalType.DATA_UPDATE:
            if not isinstance(self.value, dict):
                errors.append(f"DATA_UPDATE value must be dict, got {type(self.value)}")

        elif self.type == ProposalType.FLAG_SET:
            if not isinstance(self.value, dict):
                errors.append(f"FLAG_SET value must be dict, got {type(self.value)}")

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
    intent_tracker: 'IntentTracker'
    context_envelope: Optional['ContextEnvelope']
    turn_number: int
    persona: str
    state_config: Dict[str, Any]
    flow_config: Dict[str, Any]
    # FUNDAMENTAL FIX: state_to_phase mapping for custom flows (BANT, MEDDIC, etc.)
    # Built from FlowConfig.state_to_phase property
    state_to_phase: Dict[str, str] = field(default_factory=dict)
    # Multi-tenancy support (DESIGN_PRINCIPLES.md Section 6)
    tenant_id: str = "default"
    tenant_config: Optional['TenantConfig'] = None

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

        FUNDAMENTAL FIX: Uses state_to_phase mapping for custom flows.
        Resolution order:
        1. state_config.phase (explicit in state definition, e.g., SPIN)
        2. state_to_phase reverse mapping (from flow.phases.mapping)
        """
        # 1. Check explicit phase in state config
        explicit_phase = self.state_config.get("phase") or self.state_config.get("spin_phase")
        if explicit_phase:
            return explicit_phase
        # 2. Use state_to_phase mapping (from FlowConfig)
        return self.state_to_phase.get(self.state)

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
