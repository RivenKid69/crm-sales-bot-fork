# src/blackboard/protocols.py

"""
Protocols defining the contracts (ports) for Blackboard architecture.
Following Hexagonal Architecture pattern from DESIGN_PRINCIPLES.md.

These protocols enable:
- Static type checking with mypy
- Dependency Inversion (depend on abstractions, not concretions)
- Easy mocking in tests
- Clear boundaries between components
"""

from typing import Protocol, Dict, Any, Optional, runtime_checkable
from dataclasses import dataclass, field


@runtime_checkable
class IStateMachine(Protocol):
    """
    Input Port: Contract for state machine implementations.

    Allows DialogueBlackboard to work with any state machine
    that implements this protocol.

    IMPORTANT: StateMachine remains the storage layer. Blackboard replaces ONLY
    the process() method. All other methods (disambiguation, increment_turn)
    remain in StateMachine and are called directly from bot.py.

    Methods that Blackboard USES (via protocol):
    - state (read/write) - DEPRECATED for direct write, use transition_to()
    - collected_data (read)
    - update_data() (write)
    - current_phase (read/write) - DEPRECATED for direct write, use transition_to()
    - last_action (write) - DEPRECATED for direct write, use transition_to()
    - is_final()
    - transition_to() - RECOMMENDED: atomic state transition with consistency

    Methods that bot.py calls DIRECTLY (out of scope for Blackboard):
    - increment_turn() - for disambiguation cooldown
    - enter_disambiguation() / exit_disambiguation() / resolve_disambiguation()
    - in_disambiguation / disambiguation_context / turns_since_last_disambiguation
    - reset() - for new conversation

    STATE MUTATION POLICY:
    All state changes SHOULD go through transition_to() to ensure atomicity
    and consistency between state, current_phase, and last_action.
    Direct assignment to state is supported for backward compatibility but
    may lead to inconsistencies (e.g., state != phase mismatch).
    """

    @property
    def state(self) -> str:
        """Get current dialogue state."""
        ...

    @state.setter
    def state(self, value: str) -> None:
        """Set current dialogue state."""
        ...

    @property
    def collected_data(self) -> Dict[str, Any]:
        """Get collected data dictionary."""
        ...

    @property
    def current_phase(self) -> Optional[str]:
        """Get current dialogue phase (e.g., SPIN phase)."""
        ...

    @current_phase.setter
    def current_phase(self, value: Optional[str]) -> None:
        """Set current dialogue phase."""
        ...

    @property
    def last_action(self) -> Optional[str]:
        """Get last action taken."""
        ...

    @last_action.setter
    def last_action(self, value: Optional[str]) -> None:
        """Set last action taken."""
        ...

    def update_data(self, data: Dict[str, Any]) -> None:
        """
        Update collected data with new values.

        Called by _apply_side_effects() to persist data_updates
        from ResolvedDecision.
        """
        ...

    def is_final(self) -> bool:
        """Check if current state is final."""
        ...

    def transition_to(
        self,
        next_state: str,
        action: Optional[str] = None,
        phase: Optional[str] = None,
        source: str = "unknown",
        validate: bool = True,
    ) -> bool:
        """
        Atomically transition to a new state with consistent updates.

        This method is the SINGLE POINT OF CONTROL for state changes,
        ensuring that state, current_phase, and last_action are always
        consistent with each other.

        Args:
            next_state: Target state to transition to
            action: Action that triggered this transition (optional)
            phase: Phase for the new state (computed from config if not provided)
            source: Identifier for debugging (e.g., "orchestrator", "policy_override")
            validate: If True, validate that next_state exists in flow config

        Returns:
            True if transition was successful, False if validation failed
        """
        ...

    def sync_phase_from_state(self) -> None:
        """
        Synchronize current_phase with the current state.

        Call this after external code directly modifies state_machine.state
        to ensure current_phase is consistent.
        """
        ...


@runtime_checkable
class IIntentTracker(Protocol):
    """
    Input Port: Contract for intent tracking.
    """

    @property
    def turn_number(self) -> int:
        """Get current turn number."""
        ...

    @property
    def prev_intent(self) -> Optional[str]:
        """Get previous intent."""
        ...

    def record(self, intent: str, state: str) -> None:
        """Record an intent."""
        ...

    def objection_consecutive(self) -> int:
        """Get consecutive objection count."""
        ...

    def objection_total(self) -> int:
        """Get total objection count."""
        ...

    def total_count(self, intent: str) -> int:
        """Get total count for specific intent."""
        ...

    def category_total(self, category: str) -> int:
        """Get total count for intent category."""
        ...


@runtime_checkable
class IFlowConfig(Protocol):
    """
    Input Port: Contract for flow configuration.
    """

    @property
    def states(self) -> Dict[str, Dict[str, Any]]:
        """Get states configuration."""
        ...

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        ...

    @property
    def phase_mapping(self) -> Dict[str, str]:
        """Get phase -> state mapping."""
        ...

    @property
    def state_to_phase(self) -> Dict[str, str]:
        """Get state -> phase mapping (reverse of phase_mapping)."""
        ...

    def get_phase_for_state(self, state_name: str) -> Optional[str]:
        """
        Get phase name for a state.

        This is the CANONICAL method for resolving state -> phase mapping.
        All components should use this method.
        """
        ...

    def is_phase_state(self, state_name: str) -> bool:
        """Check if a state is a phase state."""
        ...


@runtime_checkable
class IContextEnvelope(Protocol):
    """
    Input Port: Contract for context envelope (Phase 5).
    """

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        ...


@runtime_checkable
class ITenantConfig(Protocol):
    """
    Input Port: Contract for tenant configuration.

    Supports multi-tenancy as described in DESIGN_PRINCIPLES.md Section 6.
    """

    @property
    def tenant_id(self) -> str:
        """Unique tenant identifier."""
        ...

    @property
    def bot_name(self) -> str:
        """Tenant's bot name."""
        ...

    @property
    def tone(self) -> str:
        """Tenant's preferred tone (professional, friendly, formal)."""
        ...

    @property
    def features(self) -> Dict[str, bool]:
        """Tenant-specific feature flags."""
        ...

    @property
    def persona_limits_override(self) -> Optional[Dict[str, Dict[str, int]]]:
        """Tenant-specific persona limits override."""
        ...


@dataclass
class TenantConfig:
    """
    Default implementation of ITenantConfig.

    Can be loaded from YAML or database per tenant.
    """
    tenant_id: str
    bot_name: str = "Assistant"
    tone: str = "professional"
    features: Dict[str, bool] = field(default_factory=dict)
    persona_limits_override: Optional[Dict[str, Dict[str, int]]] = None


# Default tenant for single-tenant deployments
DEFAULT_TENANT = TenantConfig(tenant_id="default")
