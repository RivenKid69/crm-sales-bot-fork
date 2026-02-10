# src/blackboard/source_registry.py

"""
Source Registry for Dialogue Blackboard System.

This module implements the Plugin Architecture pattern for Knowledge Sources,
allowing dynamic registration, configuration-driven enabling/disabling,
and ordered instantiation.
"""

from dataclasses import dataclass
import logging
from threading import RLock
from typing import Any, Callable, Dict, List, Optional, Type

from src.blackboard.knowledge_source import KnowledgeSource

logger = logging.getLogger(__name__)


@dataclass
class SourceRegistration:
    """
    Registration entry for a Knowledge Source.

    Attributes:
        source_class: The KnowledgeSource class (not instance)
        name: Unique name for this source
        priority_order: Order in which sources are called (lower = earlier)
        enabled_by_default: Whether source is enabled by default
        config_key: Key in constants.yaml for source-specific config
        description: Human-readable description
    """

    source_class: Type[KnowledgeSource]
    name: str
    priority_order: int = 100
    enabled_by_default: bool = True
    config_key: Optional[str] = None
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.source_class.__name__


@dataclass(frozen=True)
class BuiltinEnsureResult:
    """Structured result of built-in source bootstrap."""

    added: List[str]
    existing: List[str]
    conflicts: Dict[str, str]

    @property
    def ok(self) -> bool:
        return not self.conflicts


# Canonical built-in names used for bootstrap checks in composition root.
BUILTIN_SOURCE_NAMES = (
    "GoBackGuardSource",
    "ConversationGuardSource",
    "DisambiguationSource",
    "PriceQuestionSource",
    "FactQuestionSource",
    "DataCollectorSource",
    "IntentPatternGuardSource",
    "ObjectionGuardSource",
    "ObjectionReturnSource",
    "IntentProcessorSource",
    "AutonomousDecisionSource",
    "PhaseExhaustedSource",
    "StallGuardSource",
    "TransitionResolverSource",
    "EscalationSource",
)


def _get_builtin_source_specs() -> List[Dict[str, Any]]:
    """Get built-in source registration specs (lazy imports)."""

    from .sources.autonomous_decision import AutonomousDecisionSource
    from .sources.conversation_guard_ks import ConversationGuardSource
    from .sources.data_collector import DataCollectorSource
    from .sources.disambiguation import DisambiguationSource
    from .sources.escalation import EscalationSource
    from .sources.fact_question import FactQuestionSource
    from .sources.go_back_guard import GoBackGuardSource
    from .sources.intent_pattern_guard import IntentPatternGuardSource
    from .sources.intent_processor import IntentProcessorSource
    from .sources.objection_guard import ObjectionGuardSource
    from .sources.objection_return import ObjectionReturnSource
    from .sources.phase_exhausted import PhaseExhaustedSource
    from .sources.price_question import PriceQuestionSource
    from .sources.stall_guard import StallGuardSource
    from .sources.transition_resolver import TransitionResolverSource

    return [
        {
            "source_class": GoBackGuardSource,
            "name": "GoBackGuardSource",
            "priority_order": 5,
            "config_key": "go_back_guard",
            "description": "Enforces go_back limits via CircularFlowManager",
        },
        {
            "source_class": ConversationGuardSource,
            "name": "ConversationGuardSource",
            "priority_order": 7,
            "config_key": "conversation_guard",
            "enabled_by_default": True,
            "description": "Conversation safety: loops, timeouts, frustration detection",
        },
        {
            "source_class": DisambiguationSource,
            "name": "DisambiguationSource",
            "priority_order": 8,
            "config_key": "disambiguation",
            "description": "Handles disambiguation as blocking Blackboard proposal",
        },
        {
            "source_class": PriceQuestionSource,
            "name": "PriceQuestionSource",
            "priority_order": 10,
            "config_key": "price_question",
            "description": "Handles price-related questions with combinable actions",
        },
        {
            "source_class": FactQuestionSource,
            "name": "FactQuestionSource",
            "priority_order": 15,
            "config_key": "fact_question_source",
            "description": "Handles fact-based questions (features, integrations, technical, etc.)",
        },
        {
            "source_class": DataCollectorSource,
            "name": "DataCollectorSource",
            "priority_order": 20,
            "config_key": "data_collector",
            "description": "Tracks data completeness and proposes transitions",
        },
        {
            "source_class": IntentPatternGuardSource,
            "name": "IntentPatternGuardSource",
            "priority_order": 25,
            "config_key": "intent_pattern_guard",
            "enabled_by_default": True,
            "description": "Configurable intent pattern detection (comparison fatigue, etc.)",
        },
        {
            "source_class": ObjectionGuardSource,
            "name": "ObjectionGuardSource",
            "priority_order": 30,
            "config_key": "objection_guard",
            "description": "Monitors objection limits per persona",
        },
        {
            "source_class": ObjectionReturnSource,
            "name": "ObjectionReturnSource",
            "priority_order": 35,
            "config_key": "objection_return",
            "description": "Returns to previous phase after successful objection handling",
        },
        {
            "source_class": IntentProcessorSource,
            "name": "IntentProcessorSource",
            "priority_order": 40,
            "config_key": "intent_processor",
            "description": "Maps intents to actions via rules",
        },
        {
            "source_class": AutonomousDecisionSource,
            "name": "AutonomousDecisionSource",
            "priority_order": 42,
            "config_key": "autonomous_decision",
            "description": "LLM-driven state transitions for autonomous flow",
        },
        {
            "source_class": PhaseExhaustedSource,
            "name": "PhaseExhaustedSource",
            "priority_order": 43,
            "config_key": "phase_exhausted",
            "description": "Offers options menu when phase exhausted without progress",
        },
        {
            "source_class": StallGuardSource,
            "name": "StallGuardSource",
            "priority_order": 45,
            "config_key": "stall_guard",
            "description": "Universal max-turns-in-state safety net",
        },
        {
            "source_class": TransitionResolverSource,
            "name": "TransitionResolverSource",
            "priority_order": 50,
            "config_key": "transition_resolver",
            "description": "Handles intent-based state transitions",
        },
        {
            "source_class": EscalationSource,
            "name": "EscalationSource",
            "priority_order": 60,
            "config_key": "escalation",
            "description": "Detects escalation triggers for human handoff",
        },
    ]


class SourceRegistry:
    """
    Registry for Knowledge Sources following Plugin Architecture pattern.

    This registry allows:
        - Dynamic registration of Knowledge Sources
        - Configuration-driven enabling/disabling of sources
        - Ordered instantiation of sources
        - Runtime addition of custom sources
    """

    _registry: Dict[str, SourceRegistration] = {}
    _frozen: bool = False
    _lock = RLock()

    @classmethod
    def register(
        cls,
        source_class: Type[KnowledgeSource],
        name: Optional[str] = None,
        priority_order: int = 100,
        enabled_by_default: bool = True,
        config_key: Optional[str] = None,
        description: str = "",
    ) -> None:
        """Register a Knowledge Source class."""
        if not issubclass(source_class, KnowledgeSource):
            raise TypeError(f"{source_class} must be a subclass of KnowledgeSource")

        registration_name = name or source_class.__name__

        with cls._lock:
            if registration_name in cls._registry and cls._frozen:
                raise ValueError(
                    f"Source '{registration_name}' is already registered and registry is frozen"
                )

            cls._registry[registration_name] = SourceRegistration(
                source_class=source_class,
                name=registration_name,
                priority_order=priority_order,
                enabled_by_default=enabled_by_default,
                config_key=config_key,
                description=description,
            )

        logger.debug("Registered Knowledge Source: %s (order=%s)", registration_name, priority_order)

    @classmethod
    def unregister(cls, name: str) -> bool:
        """Unregister a Knowledge Source."""
        with cls._lock:
            if cls._frozen:
                raise RuntimeError("Cannot unregister from frozen registry")

            if name in cls._registry:
                del cls._registry[name]
                logger.debug("Unregistered Knowledge Source: %s", name)
                return True
            return False

    @classmethod
    def get_registration(cls, name: str) -> Optional[SourceRegistration]:
        """Get registration info for a source."""
        with cls._lock:
            return cls._registry.get(name)

    @classmethod
    def list_registered(cls) -> List[str]:
        """List all registered source names in priority order."""
        with cls._lock:
            sorted_regs = sorted(cls._registry.values(), key=lambda r: r.priority_order)
            return [r.name for r in sorted_regs]

    @classmethod
    def create_sources(
        cls,
        config: Optional[Dict[str, Any]] = None,
        source_configs: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> List[KnowledgeSource]:
        """Create instances of all enabled Knowledge Sources."""
        config = config or {}
        source_configs = source_configs or {}

        sources_config = config.get("sources", {})

        # Snapshot registrations while holding lock; instantiate outside lock.
        with cls._lock:
            sorted_regs = sorted(cls._registry.values(), key=lambda r: r.priority_order)

        sources: List[KnowledgeSource] = []

        for reg in sorted_regs:
            source_cfg = sources_config.get(reg.name, {})
            is_enabled = source_cfg.get("enabled", reg.enabled_by_default)
            if not is_enabled:
                logger.debug("Source %s is disabled by config", reg.name)
                continue

            init_kwargs = source_configs.get(reg.name, {})
            init_kwargs["name"] = reg.name

            try:
                source = reg.source_class(**init_kwargs)
                sources.append(source)
                logger.debug("Created source instance: %s", reg.name)
            except Exception as exc:
                logger.error("Failed to create source %s: %s", reg.name, exc)
                raise

        logger.info("Created %s Knowledge Sources", len(sources))
        return sources

    @classmethod
    def freeze(cls) -> None:
        """Freeze registry to prevent further modifications."""
        with cls._lock:
            cls._frozen = True
        logger.info("SourceRegistry frozen")

    @classmethod
    def reset(cls) -> None:
        """Reset registry (mainly for testing)."""
        with cls._lock:
            cls._registry.clear()
            cls._frozen = False
        logger.debug("SourceRegistry reset")

    @classmethod
    def ensure_builtin_sources(cls) -> BuiltinEnsureResult:
        """
        Ensure built-in sources are present in the registry.

        Idempotent behavior:
        - Existing built-ins with same class are preserved.
        - Missing built-ins are registered.
        - Name conflicts are reported explicitly.
        """
        added: List[str] = []
        existing: List[str] = []
        conflicts: Dict[str, str] = {}

        with cls._lock:
            for spec in _get_builtin_source_specs():
                name = spec["name"]
                source_class = spec["source_class"]
                current = cls._registry.get(name)

                if current is None:
                    if cls._frozen:
                        conflicts[name] = "registry is frozen; cannot register missing built-in"
                        continue
                    cls._registry[name] = SourceRegistration(**spec)
                    added.append(name)
                    continue

                if current.source_class is source_class:
                    existing.append(name)
                    continue

                current_cls = f"{current.source_class.__module__}.{current.source_class.__name__}"
                expected_cls = f"{source_class.__module__}.{source_class.__name__}"
                conflicts[name] = (
                    f"name occupied by different class: registered={current_cls}, expected={expected_cls}"
                )

        return BuiltinEnsureResult(added=added, existing=existing, conflicts=conflicts)


# === Decorator for easy registration ===

def register_source(
    name: Optional[str] = None,
    priority_order: int = 100,
    enabled_by_default: bool = True,
    config_key: Optional[str] = None,
    description: str = "",
) -> Callable[[Type[KnowledgeSource]], Type[KnowledgeSource]]:
    """
    Decorator to register a Knowledge Source class.

    Usage:
        @register_source(priority_order=10, description="Handles price questions")
        class PriceQuestionSource(KnowledgeSource):
            ...
    """

    def decorator(cls: Type[KnowledgeSource]) -> Type[KnowledgeSource]:
        SourceRegistry.register(
            source_class=cls,
            name=name,
            priority_order=priority_order,
            enabled_by_default=enabled_by_default,
            config_key=config_key,
            description=description,
        )
        return cls

    return decorator


# === Built-in sources registration ===

def register_builtin_sources() -> None:
    """
    Register all built-in Knowledge Sources.

    This function is idempotent and conflict-aware.
    """
    result = SourceRegistry.ensure_builtin_sources()
    if result.conflicts:
        details = "; ".join(f"{name}: {reason}" for name, reason in sorted(result.conflicts.items()))
        raise ValueError(f"Built-in source registration conflicts: {details}")

    logger.info(
        "Built-in source bootstrap: added=%s existing=%s total_registered=%s",
        len(result.added),
        len(result.existing),
        len(SourceRegistry.list_registered()),
    )
