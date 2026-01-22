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

Key Components (Stage 5 - KnowledgeSource and SourceRegistry):
- KnowledgeSource: Abstract base class for knowledge sources
- SourceRegistry: Plugin registry for knowledge sources
- SourceRegistration: Registration entry dataclass
- register_source: Decorator for easy source registration

Key Components (Stage 9 - DialogueEventBus):
- EventType: Enum for event types
- DialogueEvent: Base class for all dialogue events
- TurnStartedEvent: Event emitted when a new turn begins
- SourceContributedEvent: Event emitted when a Knowledge Source contributes
- ProposalValidatedEvent: Event emitted after proposal validation
- ConflictResolvedEvent: Event emitted after conflict resolution
- DecisionCommittedEvent: Event emitted when decision is committed
- StateTransitionedEvent: Event emitted when state actually changes
- ErrorOccurredEvent: Event emitted when an error occurs
- EventHandler: Type alias for event handlers
- DialogueEventBus: Event bus for observability and analytics
- MetricsCollector: Subscriber that collects metrics from events
- DebugLogger: Subscriber that logs detailed debug information

Key Components (Stage 10 - DialogueOrchestrator):
- DialogueOrchestrator: Main coordinator for the Dialogue Blackboard System
- create_orchestrator: Factory function to create a fully configured orchestrator
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
from .knowledge_source import KnowledgeSource
from .source_registry import (
    SourceRegistration,
    SourceRegistry,
    register_source,
)
from .event_bus import (
    EventType,
    DialogueEvent,
    TurnStartedEvent,
    SourceContributedEvent,
    ProposalValidatedEvent,
    ConflictResolvedEvent,
    DecisionCommittedEvent,
    StateTransitionedEvent,
    ErrorOccurredEvent,
    EventHandler,
    DialogueEventBus,
    MetricsCollector,
    DebugLogger,
)
from .orchestrator import (
    DialogueOrchestrator,
    create_orchestrator,
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
    # KnowledgeSource and SourceRegistry (Stage 5)
    "KnowledgeSource",
    "SourceRegistration",
    "SourceRegistry",
    "register_source",
    # Event Bus (Stage 9)
    "EventType",
    "DialogueEvent",
    "TurnStartedEvent",
    "SourceContributedEvent",
    "ProposalValidatedEvent",
    "ConflictResolvedEvent",
    "DecisionCommittedEvent",
    "StateTransitionedEvent",
    "ErrorOccurredEvent",
    "EventHandler",
    "DialogueEventBus",
    "MetricsCollector",
    "DebugLogger",
    # Orchestrator (Stage 10)
    "DialogueOrchestrator",
    "create_orchestrator",
]
