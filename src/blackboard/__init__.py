# src/blackboard/__init__.py

"""
Dialogue Blackboard System.

A blackboard-based architecture for dialogue management that replaces
the legacy rule-based state machine processing.

Key Components (Stage 1 - Enums and Protocols):
- Priority: Enum for proposal priority levels
- ProposalType: Enum for types of proposals
- IStateMachine: Protocol for state machine interface
- IIntentTracker: Protocol for intent tracking interface
- IFlowConfig: Protocol for flow configuration interface
- IContextEnvelope: Protocol for context envelope interface
- ITenantConfig: Protocol for tenant configuration interface
- TenantConfig: Default tenant configuration implementation
- DEFAULT_TENANT: Default tenant for single-tenant deployments

Key Components (Stage 2 - Data Models):
- Proposal: A proposal made by a Knowledge Source
- ResolvedDecision: The final decision after conflict resolution
- ContextSnapshot: Immutable snapshot of dialogue context for Knowledge Sources

Key Components (Stage 3 - DialogueBlackboard):
- DialogueBlackboard: Central shared workspace for dialogue management

Key Components (Stage 4 - Validator and Resolver):
- ValidationError: Validation error for a proposal
- ProposalValidator: Validates proposals before conflict resolution
- ResolutionTrace: Trace of conflict resolution process
- ConflictResolver: Resolves conflicts between proposals
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
from .models import (
    Proposal,
    ResolvedDecision,
    ContextSnapshot,
)
from .blackboard import DialogueBlackboard
from .proposal_validator import ValidationError, ProposalValidator
from .conflict_resolver import ResolutionTrace, ConflictResolver

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
    # Data Models
    "Proposal",
    "ResolvedDecision",
    "ContextSnapshot",
    # Blackboard
    "DialogueBlackboard",
    # Validator and Resolver (Stage 4)
    "ValidationError",
    "ProposalValidator",
    "ResolutionTrace",
    "ConflictResolver",
]
