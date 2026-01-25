"""
Universal Refinement Pipeline Architecture.

Provides a pluggable, extensible architecture for classification refinement
with Registry pattern and YAML configuration.

This module is the Single Source of Truth (SSoT) for the refinement pipeline.
All refinement layers must implement IRefinementLayer protocol and register
themselves with the RefinementLayerRegistry.

Architecture:
    message → Classifier → RefinementPipeline → [Layer1] → [Layer2] → ... → result

Design Principles:
    - OCP: New layers can be added without modifying pipeline code
    - DIP: Pipeline depends on abstractions (IRefinementLayer), not implementations
    - SRP: Each layer has single responsibility
    - Registry Pattern: Dynamic layer registration and lookup
    - Configuration-Driven: Layer order and settings from YAML
    - Fail-Safe: Individual layer failures don't crash pipeline

Usage:
    from src.classifier.refinement_pipeline import (
        get_refinement_pipeline,
        RefinementContext,
        register_refinement_layer,
    )

    # Registering a custom layer
    @register_refinement_layer("my_custom_layer")
    class MyCustomLayer(BaseRefinementLayer):
        ...

    # Using the pipeline
    pipeline = get_refinement_pipeline()
    result = pipeline.refine(message, classification_result, context)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    List,
    Optional,
    Protocol,
    Set,
    Type,
    TypeVar,
    runtime_checkable,
)
import logging
import time
from functools import wraps

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS
# =============================================================================

class RefinementDecision(Enum):
    """Decision made by refinement layer."""
    PASS_THROUGH = "pass_through"  # No refinement needed
    REFINED = "refined"            # Intent was refined
    SKIPPED = "skipped"            # Layer skipped (disabled or not applicable)
    ERROR = "error"                # Layer encountered error


class LayerPriority(Enum):
    """Priority levels for refinement layers.

    Higher priority layers run first.
    """
    CRITICAL = 100    # Run first (e.g., data extraction)
    HIGH = 75         # High priority refinements
    NORMAL = 50       # Default priority
    LOW = 25          # Low priority, runs last
    FALLBACK = 0      # Final fallback layers


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class RefinementContext:
    """
    Universal context for all refinement layers.

    Contains all information that any layer might need for refinement decisions.
    Layers should access only the fields they need.

    Attributes:
        message: User's original message text
        state: Current state machine state
        phase: Current dialogue phase (SPIN, BANT, etc.)
        last_action: Last action performed by the bot
        last_intent: Previous user intent
        last_bot_message: Last message from bot (for topic alignment)
        turn_number: Current turn number in conversation
        collected_data: Data collected so far in the conversation
        expects_data_type: Type of data the bot expects (from action config)

        # Objection-specific context
        last_objection_turn: Turn number of last objection
        last_objection_type: Type of last objection

        # Classification result context
        intent: Current classified intent
        confidence: Current classification confidence
        extracted_data: Data extracted from message

        # Extensible metadata
        metadata: Additional context that layers can use/modify
    """
    # Core context
    message: str
    state: Optional[str] = None
    phase: Optional[str] = None
    last_action: Optional[str] = None
    last_intent: Optional[str] = None
    last_bot_message: Optional[str] = None
    turn_number: int = 0

    # Collected data
    collected_data: Dict[str, Any] = field(default_factory=dict)
    expects_data_type: Optional[str] = None

    # Objection context
    last_objection_turn: Optional[int] = None
    last_objection_type: Optional[str] = None

    # Classification context
    intent: str = "unclear"
    confidence: float = 0.0
    extracted_data: Dict[str, Any] = field(default_factory=dict)

    # Extensible metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def update_from_result(self, result: Dict[str, Any]) -> "RefinementContext":
        """
        Create new context with updated classification fields from result.

        Used between layers to pass refined classification.

        Args:
            result: Classification result dict

        Returns:
            New RefinementContext with updated fields
        """
        return RefinementContext(
            message=self.message,
            state=self.state,
            phase=self.phase,
            last_action=self.last_action,
            last_intent=self.last_intent,
            last_bot_message=self.last_bot_message,
            turn_number=self.turn_number,
            collected_data=self.collected_data,
            expects_data_type=self.expects_data_type,
            last_objection_turn=self.last_objection_turn,
            last_objection_type=self.last_objection_type,
            intent=result.get("intent", self.intent),
            confidence=result.get("confidence", self.confidence),
            extracted_data=result.get("extracted_data", self.extracted_data),
            metadata={**self.metadata, **result.get("refinement_metadata", {})},
        )


@dataclass
class RefinementResult:
    """
    Universal result from refinement layer.

    Attributes:
        decision: What the layer decided to do
        intent: Final intent (refined or original)
        confidence: Final confidence
        original_intent: Original intent before refinement (if refined)
        refinement_reason: Code explaining why refinement was applied
        layer_name: Name of the layer that produced this result
        extracted_data: Updated extracted data (if any)
        secondary_signals: Additional signals detected (e.g., urgency, impatience)
        metadata: Additional metadata for downstream processing
        processing_time_ms: Time spent in this layer
    """
    decision: RefinementDecision
    intent: str
    confidence: float
    original_intent: Optional[str] = None
    refinement_reason: Optional[str] = None
    layer_name: str = "unknown"
    extracted_data: Dict[str, Any] = field(default_factory=dict)
    secondary_signals: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    processing_time_ms: float = 0.0

    @property
    def refined(self) -> bool:
        """Whether refinement was applied."""
        return self.decision == RefinementDecision.REFINED

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for merging with classification result."""
        result = {
            "intent": self.intent,
            "confidence": self.confidence,
        }

        if self.refined:
            result["refined"] = True
            result["original_intent"] = self.original_intent
            result["refinement_reason"] = self.refinement_reason
            result["refinement_layer"] = self.layer_name

        if self.extracted_data:
            result["extracted_data"] = self.extracted_data

        if self.secondary_signals:
            result["secondary_signals"] = self.secondary_signals

        if self.metadata:
            result["refinement_metadata"] = self.metadata

        return result


# =============================================================================
# PROTOCOL (INTERFACE)
# =============================================================================

@runtime_checkable
class IRefinementLayer(Protocol):
    """
    Protocol (interface) for refinement layers.

    All refinement layers must implement this protocol.
    This ensures consistent behavior across all layers.

    Implementation Requirements:
        - name: Unique identifier for the layer
        - priority: When to run (higher = earlier)
        - should_apply(): Check if layer should process this message
        - refine(): Apply refinement logic
        - get_stats(): Return monitoring statistics
    """

    @property
    def name(self) -> str:
        """Unique name of this layer."""
        ...

    @property
    def priority(self) -> LayerPriority:
        """Priority level for layer ordering."""
        ...

    @property
    def enabled(self) -> bool:
        """Whether this layer is enabled."""
        ...

    def should_apply(self, ctx: RefinementContext) -> bool:
        """
        Check if this layer should process the message.

        Fast check to avoid unnecessary processing.

        Args:
            ctx: Refinement context

        Returns:
            True if layer should process, False to skip
        """
        ...

    def refine(
        self,
        message: str,
        result: Dict[str, Any],
        ctx: RefinementContext
    ) -> RefinementResult:
        """
        Apply refinement logic to classification result.

        Args:
            message: User's message
            result: Current classification result
            ctx: Refinement context

        Returns:
            RefinementResult with decision and potentially refined classification
        """
        ...

    def get_stats(self) -> Dict[str, Any]:
        """Get monitoring statistics for this layer."""
        ...


# =============================================================================
# BASE CLASS
# =============================================================================

T = TypeVar("T", bound="BaseRefinementLayer")


class BaseRefinementLayer(ABC):
    """
    Abstract base class for refinement layers.

    Provides common functionality:
    - Feature flag integration
    - Error handling (fail-safe)
    - Statistics tracking
    - Logging

    Subclasses must implement:
    - _should_apply(): Layer-specific applicability check
    - _do_refine(): Layer-specific refinement logic

    Optional overrides:
    - _get_config(): Load layer-specific config
    """

    # Class-level configuration
    LAYER_NAME: ClassVar[str] = "base"
    LAYER_PRIORITY: ClassVar[LayerPriority] = LayerPriority.NORMAL
    FEATURE_FLAG: ClassVar[Optional[str]] = None  # Feature flag name, if any

    def __init__(self):
        """Initialize the layer with config and stats."""
        self._config = self._get_config()
        self._enabled = self._check_enabled()

        # Statistics
        self._calls_total = 0
        self._refinements_total = 0
        self._errors_total = 0
        self._skips_total = 0
        self._total_time_ms = 0.0
        self._refinements_by_reason: Dict[str, int] = {}

        logger.debug(
            f"{self.name} initialized",
            extra={
                "layer": self.name,
                "priority": self.priority.name,
                "enabled": self._enabled,
            }
        )

    # -------------------------------------------------------------------------
    # Protocol implementation
    # -------------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Unique name of this layer."""
        return self.LAYER_NAME

    @property
    def priority(self) -> LayerPriority:
        """Priority level for layer ordering."""
        return self.LAYER_PRIORITY

    @property
    def enabled(self) -> bool:
        """Whether this layer is enabled."""
        return self._enabled

    def should_apply(self, ctx: RefinementContext) -> bool:
        """
        Check if layer should process this message.

        Combines enabled check with layer-specific logic.
        """
        if not self._enabled:
            return False

        try:
            return self._should_apply(ctx)
        except Exception as e:
            logger.warning(
                f"{self.name}: should_apply failed",
                extra={"error": str(e), "layer": self.name}
            )
            return False

    def refine(
        self,
        message: str,
        result: Dict[str, Any],
        ctx: RefinementContext
    ) -> RefinementResult:
        """
        Apply refinement with error handling and stats tracking.
        """
        self._calls_total += 1
        start_time = time.perf_counter()

        try:
            # Check if we should apply
            if not self.should_apply(ctx):
                self._skips_total += 1
                return self._pass_through(result, ctx)

            # Apply refinement
            refinement_result = self._do_refine(message, result, ctx)

            # Track stats
            if refinement_result.refined:
                self._refinements_total += 1
                if refinement_result.refinement_reason:
                    self._refinements_by_reason[refinement_result.refinement_reason] = (
                        self._refinements_by_reason.get(refinement_result.refinement_reason, 0) + 1
                    )

            # Add timing
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self._total_time_ms += elapsed_ms
            refinement_result.processing_time_ms = elapsed_ms
            refinement_result.layer_name = self.name

            return refinement_result

        except Exception as e:
            self._errors_total += 1
            logger.warning(
                f"{self.name}: refinement failed, passing through",
                extra={
                    "error": str(e),
                    "layer": self.name,
                    "user_message": message[:50],
                    "intent": result.get("intent"),
                },
                exc_info=True
            )
            return self._pass_through(result, ctx, error=str(e))

    def get_stats(self) -> Dict[str, Any]:
        """Get monitoring statistics."""
        avg_time = (
            self._total_time_ms / self._calls_total
            if self._calls_total > 0 else 0.0
        )

        return {
            "layer": self.name,
            "enabled": self._enabled,
            "priority": self.priority.name,
            "calls_total": self._calls_total,
            "refinements_total": self._refinements_total,
            "refinement_rate": (
                self._refinements_total / self._calls_total
                if self._calls_total > 0 else 0.0
            ),
            "skips_total": self._skips_total,
            "errors_total": self._errors_total,
            "avg_time_ms": avg_time,
            "refinements_by_reason": dict(self._refinements_by_reason),
        }

    # -------------------------------------------------------------------------
    # Abstract methods (must be implemented by subclasses)
    # -------------------------------------------------------------------------

    @abstractmethod
    def _should_apply(self, ctx: RefinementContext) -> bool:
        """
        Layer-specific check if refinement should be applied.

        Called after enabled check passes.

        Args:
            ctx: Refinement context

        Returns:
            True if this layer should process the message
        """
        ...

    @abstractmethod
    def _do_refine(
        self,
        message: str,
        result: Dict[str, Any],
        ctx: RefinementContext
    ) -> RefinementResult:
        """
        Layer-specific refinement logic.

        Called only if should_apply() returns True.

        Args:
            message: User's message
            result: Current classification result
            ctx: Refinement context

        Returns:
            RefinementResult with decision
        """
        ...

    # -------------------------------------------------------------------------
    # Optional overrides
    # -------------------------------------------------------------------------

    def _get_config(self) -> Dict[str, Any]:
        """
        Load layer-specific configuration.

        Override to load from constants.yaml or other sources.

        Returns:
            Configuration dict
        """
        return {}

    # -------------------------------------------------------------------------
    # Helper methods
    # -------------------------------------------------------------------------

    def _check_enabled(self) -> bool:
        """Check if layer is enabled via feature flag."""
        if self.FEATURE_FLAG is None:
            return True

        try:
            from feature_flags import flags
            return flags.is_enabled(self.FEATURE_FLAG)
        except ImportError:
            return True

    def _pass_through(
        self,
        result: Dict[str, Any],
        ctx: RefinementContext,
        error: Optional[str] = None
    ) -> RefinementResult:
        """Create pass-through result (no refinement)."""
        decision = RefinementDecision.ERROR if error else RefinementDecision.PASS_THROUGH

        return RefinementResult(
            decision=decision,
            intent=result.get("intent", ctx.intent),
            confidence=result.get("confidence", ctx.confidence),
            layer_name=self.name,
            extracted_data=result.get("extracted_data", {}),
            metadata={"error": error} if error else {},
        )

    def _create_refined_result(
        self,
        new_intent: str,
        new_confidence: float,
        original_intent: str,
        reason: str,
        result: Dict[str, Any],
        extracted_data: Optional[Dict[str, Any]] = None,
        secondary_signals: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RefinementResult:
        """Create a refined result."""
        return RefinementResult(
            decision=RefinementDecision.REFINED,
            intent=new_intent,
            confidence=new_confidence,
            original_intent=original_intent,
            refinement_reason=reason,
            layer_name=self.name,
            extracted_data=extracted_data or result.get("extracted_data", {}),
            secondary_signals=secondary_signals or [],
            metadata=metadata or {},
        )


# =============================================================================
# REGISTRY
# =============================================================================

class RefinementLayerRegistry:
    """
    Registry for refinement layers.

    Implements the Registry pattern for dynamic layer registration and lookup.
    Layers are registered by name and can be retrieved for pipeline construction.

    Thread Safety:
        This class is NOT thread-safe for registration (design choice).
        Registration should happen at module load time, not runtime.
        Lookup operations are thread-safe.

    Usage:
        # Registration (at module load)
        registry = RefinementLayerRegistry.get_registry()
        registry.register("my_layer", MyLayerClass)

        # Or using decorator
        @register_refinement_layer("my_layer")
        class MyLayerClass(BaseRefinementLayer):
            ...

        # Lookup
        layer_class = registry.get("my_layer")
        layer = layer_class()
    """

    _instance: Optional["RefinementLayerRegistry"] = None

    def __init__(self):
        """Initialize empty registry."""
        self._layers: Dict[str, Type[BaseRefinementLayer]] = {}
        self._instances: Dict[str, BaseRefinementLayer] = {}

    @classmethod
    def get_registry(cls) -> "RefinementLayerRegistry":
        """Get singleton registry instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (for testing)."""
        cls._instance = None

    def register(
        self,
        name: str,
        layer_class: Type[BaseRefinementLayer],
        override: bool = False
    ) -> None:
        """
        Register a refinement layer class.

        Args:
            name: Unique name for the layer
            layer_class: Layer class (must inherit from BaseRefinementLayer)
            override: If True, allow overriding existing registration

        Raises:
            ValueError: If name already registered and override=False
            TypeError: If layer_class doesn't inherit from BaseRefinementLayer
        """
        if name in self._layers and not override:
            raise ValueError(
                f"Layer '{name}' already registered. "
                f"Use override=True to replace."
            )

        if not issubclass(layer_class, BaseRefinementLayer):
            raise TypeError(
                f"Layer class must inherit from BaseRefinementLayer, "
                f"got {layer_class.__name__}"
            )

        self._layers[name] = layer_class
        # Clear cached instance
        self._instances.pop(name, None)

        logger.debug(f"Registered refinement layer: {name}")

    def get(self, name: str) -> Optional[Type[BaseRefinementLayer]]:
        """Get layer class by name."""
        return self._layers.get(name)

    def get_layer_instance(self, name: str) -> Optional[BaseRefinementLayer]:
        """
        Get or create layer instance by name.

        Instances are cached for reuse.
        """
        if name not in self._instances:
            layer_class = self._layers.get(name)
            if layer_class is None:
                return None
            self._instances[name] = layer_class()

        return self._instances.get(name)

    def get_all_names(self) -> List[str]:
        """Get all registered layer names."""
        return list(self._layers.keys())

    def get_all_instances(self) -> List[BaseRefinementLayer]:
        """Get instances of all registered layers."""
        instances = []
        for name in self._layers:
            instance = self.get_layer_instance(name)
            if instance:
                instances.append(instance)
        return instances

    def is_registered(self, name: str) -> bool:
        """Check if layer is registered."""
        return name in self._layers


def register_refinement_layer(
    name: str,
    override: bool = False
) -> Callable[[Type[T]], Type[T]]:
    """
    Decorator to register a refinement layer class.

    Usage:
        @register_refinement_layer("my_layer")
        class MyLayer(BaseRefinementLayer):
            LAYER_NAME = "my_layer"
            ...

    Args:
        name: Unique name for the layer
        override: If True, allow overriding existing registration

    Returns:
        Decorator function
    """
    def decorator(cls: Type[T]) -> Type[T]:
        registry = RefinementLayerRegistry.get_registry()
        registry.register(name, cls, override=override)
        return cls

    return decorator


# =============================================================================
# PIPELINE
# =============================================================================

class RefinementPipeline:
    """
    Orchestrates refinement layers in priority order.

    The pipeline:
    1. Loads layer configuration from YAML
    2. Instantiates enabled layers from registry
    3. Sorts layers by priority (highest first)
    4. Runs each layer in sequence
    5. Passes refined result to next layer

    Fail-Safe Design:
        - Individual layer failures don't stop pipeline
        - Failed layers are skipped with warning
        - Pipeline always returns a valid result

    Configuration (constants.yaml):
        refinement_pipeline:
          enabled: true
          layers:
            - name: short_answer
              enabled: true
              priority: 75  # Optional override
            - name: composite_message
              enabled: true
            - name: objection
              enabled: true

    Usage:
        pipeline = RefinementPipeline()
        result = pipeline.refine(message, classification_result, context)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize pipeline with configuration.

        Args:
            config: Optional config dict. If None, loads from constants.yaml
        """
        self._config = config or self._load_config()
        self._enabled = self._config.get("enabled", True)
        self._layers: List[BaseRefinementLayer] = []
        self._layer_order: List[str] = []

        # Statistics
        self._calls_total = 0
        self._refinements_total = 0
        self._total_time_ms = 0.0

        # Initialize layers
        self._initialize_layers()

        logger.info(
            "RefinementPipeline initialized",
            extra={
                "enabled": self._enabled,
                "layers": [l.name for l in self._layers],
            }
        )

    def _load_config(self) -> Dict[str, Any]:
        """Load pipeline configuration from constants.yaml."""
        try:
            from src.yaml_config.constants import get_refinement_pipeline_config
            return get_refinement_pipeline_config()
        except (ImportError, AttributeError):
            logger.warning(
                "Could not load refinement_pipeline config, using defaults"
            )
            return {"enabled": True, "layers": []}

    def _initialize_layers(self) -> None:
        """Initialize layers from registry based on configuration."""
        if not self._enabled:
            logger.info("RefinementPipeline disabled by configuration")
            return

        registry = RefinementLayerRegistry.get_registry()
        layer_configs = self._config.get("layers", [])

        # If no explicit config, use all registered layers
        if not layer_configs:
            self._layers = registry.get_all_instances()
        else:
            # Load specified layers
            for layer_cfg in layer_configs:
                if isinstance(layer_cfg, str):
                    layer_name = layer_cfg
                    layer_enabled = True
                else:
                    layer_name = layer_cfg.get("name")
                    layer_enabled = layer_cfg.get("enabled", True)

                if not layer_enabled:
                    continue

                layer = registry.get_layer_instance(layer_name)
                if layer:
                    self._layers.append(layer)
                else:
                    logger.warning(
                        f"Layer '{layer_name}' not found in registry"
                    )

        # Sort by priority (highest first)
        self._layers.sort(key=lambda l: l.priority.value, reverse=True)
        self._layer_order = [l.name for l in self._layers]

    def refine(
        self,
        message: str,
        result: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Run classification through refinement pipeline.

        Args:
            message: User's message
            result: Classification result from primary classifier
            context: Dialogue context dict

        Returns:
            Refined classification result
        """
        self._calls_total += 1
        start_time = time.perf_counter()

        if not self._enabled or not self._layers:
            return result

        # Create universal context
        ctx = self._create_context(message, result, context or {})

        # Current result (will be refined by layers)
        current_result = result.copy()
        refinement_chain: List[str] = []

        # Run through layers
        for layer in self._layers:
            try:
                layer_result = layer.refine(message, current_result, ctx)

                if layer_result.refined:
                    # Update result with refinement
                    current_result.update(layer_result.to_dict())
                    refinement_chain.append(layer.name)

                    # Update context for next layer
                    ctx = ctx.update_from_result(current_result)

                    logger.debug(
                        f"Layer {layer.name} refined intent",
                        extra={
                            "layer": layer.name,
                            "original": layer_result.original_intent,
                            "refined": layer_result.intent,
                            "reason": layer_result.refinement_reason,
                        }
                    )

            except Exception as e:
                logger.error(
                    f"Layer {layer.name} failed unexpectedly",
                    extra={
                        "layer": layer.name,
                        "error": str(e),
                        "user_message": message[:50],
                    },
                    exc_info=True
                )
                # Continue to next layer

        # Add pipeline metadata
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        self._total_time_ms += elapsed_ms

        if refinement_chain:
            self._refinements_total += 1
            current_result["refinement_chain"] = refinement_chain
            current_result["pipeline_time_ms"] = elapsed_ms

        return current_result

    def _create_context(
        self,
        message: str,
        result: Dict[str, Any],
        context: Dict[str, Any]
    ) -> RefinementContext:
        """Create universal RefinementContext from inputs."""
        return RefinementContext(
            message=message,
            state=context.get("state"),
            phase=(
                context.get("current_phase") or
                context.get("spin_phase") or
                context.get("phase")
            ),
            last_action=context.get("last_action"),
            last_intent=context.get("last_intent"),
            last_bot_message=context.get("last_bot_message"),
            turn_number=context.get("turn_number", 0),
            collected_data=context.get("collected_data", {}),
            expects_data_type=context.get("expects_data_type"),
            last_objection_turn=context.get("last_objection_turn"),
            last_objection_type=context.get("last_objection_type"),
            intent=result.get("intent", "unclear"),
            confidence=result.get("confidence", 0.0),
            extracted_data=result.get("extracted_data", {}),
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get pipeline statistics."""
        avg_time = (
            self._total_time_ms / self._calls_total
            if self._calls_total > 0 else 0.0
        )

        return {
            "enabled": self._enabled,
            "layers": self._layer_order,
            "calls_total": self._calls_total,
            "refinements_total": self._refinements_total,
            "refinement_rate": (
                self._refinements_total / self._calls_total
                if self._calls_total > 0 else 0.0
            ),
            "avg_time_ms": avg_time,
            "layer_stats": {
                layer.name: layer.get_stats()
                for layer in self._layers
            },
        }

    def get_layer(self, name: str) -> Optional[BaseRefinementLayer]:
        """Get layer instance by name."""
        for layer in self._layers:
            if layer.name == name:
                return layer
        return None

    @property
    def layer_names(self) -> List[str]:
        """Get ordered list of layer names."""
        return self._layer_order.copy()


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_pipeline_instance: Optional[RefinementPipeline] = None


def get_refinement_pipeline() -> RefinementPipeline:
    """
    Get singleton pipeline instance.

    Returns:
        RefinementPipeline instance
    """
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = RefinementPipeline()
    return _pipeline_instance


def reset_refinement_pipeline() -> None:
    """Reset singleton pipeline (for testing)."""
    global _pipeline_instance
    _pipeline_instance = None
    RefinementLayerRegistry.reset()


# =============================================================================
# CONTEXT BUILDER (for convenience)
# =============================================================================

def build_refinement_context(
    message: str,
    result: Dict[str, Any],
    **kwargs: Any
) -> RefinementContext:
    """
    Convenience function to build RefinementContext.

    Args:
        message: User's message
        result: Classification result
        **kwargs: Additional context fields

    Returns:
        RefinementContext instance
    """
    return RefinementContext(
        message=message,
        intent=result.get("intent", "unclear"),
        confidence=result.get("confidence", 0.0),
        extracted_data=result.get("extracted_data", {}),
        **kwargs
    )
