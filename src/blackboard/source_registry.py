# src/blackboard/source_registry.py

"""
Source Registry for Dialogue Blackboard System.

This module implements the Plugin Architecture pattern for Knowledge Sources,
allowing dynamic registration, configuration-driven enabling/disabling,
and ordered instantiation.
"""

from typing import Dict, Type, List, Optional, Any, Callable
from dataclasses import dataclass
import logging

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

    def __post_init__(self):
        if not self.name:
            self.name = self.source_class.__name__


class SourceRegistry:
    """
    Registry for Knowledge Sources following Plugin Architecture pattern.

    This registry allows:
        - Dynamic registration of Knowledge Sources
        - Configuration-driven enabling/disabling of sources
        - Ordered instantiation of sources
        - Runtime addition of custom sources

    Usage:
        # Register built-in sources (typically in sources/__init__.py)
        SourceRegistry.register(
            PriceQuestionSource,
            name="PriceQuestionSource",
            priority_order=10,
            config_key="price_question"
        )

        # Get all enabled source instances
        sources = SourceRegistry.create_sources(config)

        # Register custom source at runtime
        SourceRegistry.register(MyCustomSource, priority_order=50)

    Design Principles:
        - Open/Closed: New sources can be added without modifying existing code
        - Configuration-driven: Sources can be enabled/disabled via YAML
        - Deterministic: Sources are always instantiated in priority_order
    """

    _registry: Dict[str, SourceRegistration] = {}
    _frozen: bool = False

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
        """
        Register a Knowledge Source class.

        Args:
            source_class: The KnowledgeSource class to register
            name: Unique name (defaults to class name)
            priority_order: Execution order (lower = earlier)
            enabled_by_default: Whether enabled when not in config
            config_key: Key in constants.yaml for source config
            description: Human-readable description

        Raises:
            ValueError: If name is already registered and registry is frozen
            TypeError: If source_class is not a KnowledgeSource subclass
        """
        if not issubclass(source_class, KnowledgeSource):
            raise TypeError(
                f"{source_class} must be a subclass of KnowledgeSource"
            )

        registration_name = name or source_class.__name__

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

        logger.debug(f"Registered Knowledge Source: {registration_name} (order={priority_order})")

    @classmethod
    def unregister(cls, name: str) -> bool:
        """
        Unregister a Knowledge Source.

        Args:
            name: Name of the source to unregister

        Returns:
            True if source was unregistered, False if not found

        Raises:
            RuntimeError: If registry is frozen
        """
        if cls._frozen:
            raise RuntimeError("Cannot unregister from frozen registry")

        if name in cls._registry:
            del cls._registry[name]
            logger.debug(f"Unregistered Knowledge Source: {name}")
            return True
        return False

    @classmethod
    def get_registration(cls, name: str) -> Optional[SourceRegistration]:
        """Get registration info for a source."""
        return cls._registry.get(name)

    @classmethod
    def list_registered(cls) -> List[str]:
        """List all registered source names in priority order."""
        sorted_regs = sorted(
            cls._registry.values(),
            key=lambda r: r.priority_order
        )
        return [r.name for r in sorted_regs]

    @classmethod
    def create_sources(
        cls,
        config: Optional[Dict[str, Any]] = None,
        source_configs: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> List[KnowledgeSource]:
        """
        Create instances of all enabled Knowledge Sources.

        Args:
            config: Global config dict (checks 'sources.{name}.enabled')
            source_configs: Per-source configuration dicts

        Returns:
            List of KnowledgeSource instances in priority order
        """
        config = config or {}
        source_configs = source_configs or {}

        # Get sources config section
        sources_config = config.get("sources", {})

        # Sort registrations by priority
        sorted_regs = sorted(
            cls._registry.values(),
            key=lambda r: r.priority_order
        )

        sources: List[KnowledgeSource] = []

        for reg in sorted_regs:
            # Check if enabled
            source_cfg = sources_config.get(reg.name, {})
            is_enabled = source_cfg.get("enabled", reg.enabled_by_default)

            if not is_enabled:
                logger.debug(f"Source {reg.name} is disabled by config")
                continue

            # Get source-specific config
            init_kwargs = source_configs.get(reg.name, {})
            init_kwargs["name"] = reg.name

            # Create instance
            try:
                source = reg.source_class(**init_kwargs)
                sources.append(source)
                logger.debug(f"Created source instance: {reg.name}")
            except Exception as e:
                logger.error(f"Failed to create source {reg.name}: {e}")
                raise

        logger.info(f"Created {len(sources)} Knowledge Sources")
        return sources

    @classmethod
    def freeze(cls) -> None:
        """Freeze registry to prevent further modifications."""
        cls._frozen = True
        logger.info("SourceRegistry frozen")

    @classmethod
    def reset(cls) -> None:
        """Reset registry (mainly for testing)."""
        cls._registry.clear()
        cls._frozen = False
        logger.debug("SourceRegistry reset")


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

    Called by DialogueOrchestrator during initialization.
    Sources are registered in recommended execution order.

    Note: This function requires all source modules to be available.
    It should only be called after stages 6-8 are complete.
    """
    from .sources.price_question import PriceQuestionSource
    from .sources.fact_question import FactQuestionSource  # FIX: Lost Question Fix
    from .sources.disambiguation import DisambiguationSource
    from .sources.data_collector import DataCollectorSource
    from .sources.objection_guard import ObjectionGuardSource
    from .sources.objection_return import ObjectionReturnSource
    from .sources.intent_processor import IntentProcessorSource
    from .sources.transition_resolver import TransitionResolverSource
    from .sources.escalation import EscalationSource
    from .sources.go_back_guard import GoBackGuardSource
    from .sources.stall_guard import StallGuardSource
    from .sources.phase_exhausted import PhaseExhaustedSource

    # Register in recommended order (lower priority_order = earlier execution)

    # FIX: GoBackGuardSource runs first to enforce go_back limits
    # Must run BEFORE TransitionResolverSource to block transitions if limit reached
    SourceRegistry.register(
        GoBackGuardSource,
        name="GoBackGuardSource",
        priority_order=5,
        config_key="go_back_guard",
        description="Enforces go_back limits via CircularFlowManager"
    )

    # DisambiguationSource: Handles disambiguation as blocking Blackboard proposal
    # After GoBackGuardSource (5), before PriceQuestionSource (10)
    # combinable=False ensures transitions are blocked while asking clarification
    SourceRegistry.register(
        DisambiguationSource,
        name="DisambiguationSource",
        priority_order=8,
        config_key="disambiguation",
        description="Handles disambiguation as blocking Blackboard proposal"
    )

    SourceRegistry.register(
        PriceQuestionSource,
        name="PriceQuestionSource",
        priority_order=10,
        config_key="price_question",
        description="Handles price-related questions with combinable actions"
    )

    # FIX: FactQuestionSource handles ALL fact-based questions universally
    # Works with SecondaryIntentDetectionLayer to detect lost questions
    # Runs after PriceQuestionSource to avoid overlap
    SourceRegistry.register(
        FactQuestionSource,
        name="FactQuestionSource",
        priority_order=15,
        config_key="fact_question_source",
        description="Handles fact-based questions (features, integrations, technical, etc.)"
    )

    SourceRegistry.register(
        DataCollectorSource,
        name="DataCollectorSource",
        priority_order=20,
        config_key="data_collector",
        description="Tracks data completeness and proposes transitions"
    )

    SourceRegistry.register(
        ObjectionGuardSource,
        name="ObjectionGuardSource",
        priority_order=30,
        config_key="objection_guard",
        description="Monitors objection limits per persona"
    )

    # FIX: ObjectionReturnSource handles returning to previous phase after objection
    # Must run AFTER ObjectionGuardSource (limit check) but BEFORE TransitionResolverSource
    # Uses HIGH priority proposals to win over YAML transitions (NORMAL priority)
    SourceRegistry.register(
        ObjectionReturnSource,
        name="ObjectionReturnSource",
        priority_order=35,
        config_key="objection_return",
        description="Returns to previous phase after successful objection handling"
    )

    SourceRegistry.register(
        IntentProcessorSource,
        name="IntentProcessorSource",
        priority_order=40,
        config_key="intent_processor",
        description="Maps intents to actions via rules"
    )

    # PhaseExhaustedSource: Offers options menu when phase stuck without progress
    # After IntentProcessorSource (40) — intent processing happens first
    # Before StallGuardSource (45) — softer mechanism fires first
    SourceRegistry.register(
        PhaseExhaustedSource,
        name="PhaseExhaustedSource",
        priority_order=43,
        config_key="phase_exhausted",
        description="Offers options menu when phase exhausted without progress"
    )

    # StallGuardSource: Universal max-turns-in-state safety net
    # After ObjectionReturnSource (35) — precise return on positive intents first
    # Before TransitionResolverSource (50) — safety net catches stuck states
    SourceRegistry.register(
        StallGuardSource,
        name="StallGuardSource",
        priority_order=45,
        config_key="stall_guard",
        description="Universal max-turns-in-state safety net"
    )

    SourceRegistry.register(
        TransitionResolverSource,
        name="TransitionResolverSource",
        priority_order=50,
        config_key="transition_resolver",
        description="Handles intent-based state transitions"
    )

    SourceRegistry.register(
        EscalationSource,
        name="EscalationSource",
        priority_order=60,
        config_key="escalation",
        description="Detects escalation triggers for human handoff"
    )

    logger.info(f"Registered {len(SourceRegistry.list_registered())} built-in sources")
