# src/blackboard/__init__.py

"""
Dialogue Blackboard System.

A blackboard-based architecture for dialogue management that replaces
the legacy rule-based state machine processing.

Key Components (Stage 1):
- Priority: Enum for proposal priority levels
- ProposalType: Enum for types of proposals
- IStateMachine: Protocol for state machine interface
- IIntentTracker: Protocol for intent tracking interface
- IFlowConfig: Protocol for flow configuration interface
- IContextEnvelope: Protocol for context envelope interface
- ITenantConfig: Protocol for tenant configuration interface
- TenantConfig: Default tenant configuration implementation
- DEFAULT_TENANT: Default tenant for single-tenant deployments
"""

from .enums import Priority, ProposalType
from .protocols import (
    IStateMachine,
    IIntentTracker,
    IFlowConfig,
    IContextEnvelope,
    ITenantConfig,
    TenantConfig,
    DEFAULT_TENANT,
)

__all__ = [
    # Enums
    "Priority",
    "ProposalType",
    # Protocols
    "IStateMachine",
    "IIntentTracker",
    "IFlowConfig",
    "IContextEnvelope",
    "ITenantConfig",
    # Implementations
    "TenantConfig",
    "DEFAULT_TENANT",
]
