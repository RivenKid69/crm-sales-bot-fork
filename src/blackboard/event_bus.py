# src/blackboard/event_bus.py

from typing import Dict, Any, List, Callable, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
import logging
import threading
from queue import Queue

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Types of events emitted by the Blackboard system."""
    TURN_STARTED = auto()
    SOURCE_CONTRIBUTED = auto()
    PROPOSAL_VALIDATED = auto()
    CONFLICT_RESOLVED = auto()
    DECISION_COMMITTED = auto()
    STATE_TRANSITIONED = auto()
    ERROR_OCCURRED = auto()


@dataclass
class DialogueEvent:
    """
    Base class for all dialogue events.

    Attributes:
        event_type: Type of the event
        timestamp: When the event occurred
        turn_number: Dialogue turn number
        data: Event-specific data
    """
    event_type: EventType
    timestamp: datetime = field(default_factory=datetime.now)
    turn_number: int = 0
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_type": self.event_type.name,
            "timestamp": self.timestamp.isoformat(),
            "turn_number": self.turn_number,
            "data": self.data,
        }


@dataclass
class TurnStartedEvent(DialogueEvent):
    """Event emitted when a new turn begins."""

    def __init__(self, turn_number: int, intent: str, state: str, **kwargs):
        super().__init__(
            event_type=EventType.TURN_STARTED,
            turn_number=turn_number,
            data={
                "intent": intent,
                "state": state,
                **kwargs
            }
        )


@dataclass
class SourceContributedEvent(DialogueEvent):
    """Event emitted when a Knowledge Source contributes proposals."""

    def __init__(
        self,
        turn_number: int,
        source_name: str,
        proposals_count: int,
        proposals_summary: List[str],
        execution_time_ms: float,
        **kwargs
    ):
        super().__init__(
            event_type=EventType.SOURCE_CONTRIBUTED,
            turn_number=turn_number,
            data={
                "source_name": source_name,
                "proposals_count": proposals_count,
                "proposals_summary": proposals_summary,
                "execution_time_ms": execution_time_ms,
                **kwargs
            }
        )


@dataclass
class ProposalValidatedEvent(DialogueEvent):
    """Event emitted after proposal validation."""

    def __init__(
        self,
        turn_number: int,
        valid_count: int,
        error_count: int,
        warning_count: int,
        errors: List[str],
        **kwargs
    ):
        super().__init__(
            event_type=EventType.PROPOSAL_VALIDATED,
            turn_number=turn_number,
            data={
                "valid_count": valid_count,
                "error_count": error_count,
                "warning_count": warning_count,
                "errors": errors,
                **kwargs
            }
        )


@dataclass
class ConflictResolvedEvent(DialogueEvent):
    """Event emitted after conflict resolution."""

    def __init__(
        self,
        turn_number: int,
        winning_action: str,
        winning_transition: Optional[str],
        rejected_count: int,
        merge_decision: str,
        resolution_time_ms: float,
        **kwargs
    ):
        super().__init__(
            event_type=EventType.CONFLICT_RESOLVED,
            turn_number=turn_number,
            data={
                "winning_action": winning_action,
                "winning_transition": winning_transition,
                "rejected_count": rejected_count,
                "merge_decision": merge_decision,
                "resolution_time_ms": resolution_time_ms,
                **kwargs
            }
        )


@dataclass
class DecisionCommittedEvent(DialogueEvent):
    """Event emitted when decision is committed to blackboard."""

    def __init__(
        self,
        turn_number: int,
        action: str,
        next_state: str,
        reason_codes: List[str],
        **kwargs
    ):
        super().__init__(
            event_type=EventType.DECISION_COMMITTED,
            turn_number=turn_number,
            data={
                "action": action,
                "next_state": next_state,
                "reason_codes": reason_codes,
                **kwargs
            }
        )


@dataclass
class StateTransitionedEvent(DialogueEvent):
    """Event emitted when state actually changes."""

    def __init__(
        self,
        turn_number: int,
        from_state: str,
        to_state: str,
        trigger_reason: str,
        **kwargs
    ):
        super().__init__(
            event_type=EventType.STATE_TRANSITIONED,
            turn_number=turn_number,
            data={
                "from_state": from_state,
                "to_state": to_state,
                "trigger_reason": trigger_reason,
                **kwargs
            }
        )


@dataclass
class ErrorOccurredEvent(DialogueEvent):
    """Event emitted when an error occurs."""

    def __init__(
        self,
        turn_number: int,
        error_type: str,
        error_message: str,
        component: str,
        **kwargs
    ):
        super().__init__(
            event_type=EventType.ERROR_OCCURRED,
            turn_number=turn_number,
            data={
                "error_type": error_type,
                "error_message": error_message,
                "component": component,
                **kwargs
            }
        )


# Type alias for event handlers
EventHandler = Callable[[DialogueEvent], None]


class DialogueEventBus:
    """
    Event bus for observability and analytics in the Blackboard system.

    Responsibilities:
        - Publish events from Blackboard components
        - Allow subscribers to listen for specific event types
        - Support async processing to avoid blocking main flow
        - Provide event history for debugging

    Subscribers can include:
        - MetricsCollector: records metrics for monitoring
        - DebugLogger: detailed logging for debugging
        - AnalyticsTracker: business analytics
        - AlertManager: alerts on anomalies
    """

    def __init__(
        self,
        async_mode: bool = False,
        history_size: int = 100
    ):
        """
        Initialize the event bus.

        Args:
            async_mode: If True, process events asynchronously
            history_size: Number of recent events to keep in history
        """
        self._handlers: Dict[EventType, List[EventHandler]] = {
            event_type: [] for event_type in EventType
        }
        self._global_handlers: List[EventHandler] = []
        self._history: List[DialogueEvent] = []
        self._history_size = history_size
        self._async_mode = async_mode
        self._event_queue: Optional[Queue] = Queue() if async_mode else None
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False

        if async_mode:
            self._start_worker()

    def subscribe(
        self,
        event_type: EventType,
        handler: EventHandler
    ) -> None:
        """
        Subscribe to a specific event type.

        Args:
            event_type: Type of event to subscribe to
            handler: Callback function to handle the event
        """
        self._handlers[event_type].append(handler)
        logger.debug(f"Handler subscribed to {event_type.name}")

    def subscribe_all(self, handler: EventHandler) -> None:
        """
        Subscribe to all event types.

        Args:
            handler: Callback function to handle all events
        """
        self._global_handlers.append(handler)
        logger.debug("Global handler subscribed to all events")

    def unsubscribe(
        self,
        event_type: EventType,
        handler: EventHandler
    ) -> None:
        """
        Unsubscribe from a specific event type.

        Args:
            event_type: Type of event to unsubscribe from
            handler: Handler to remove
        """
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)
            logger.debug(f"Handler unsubscribed from {event_type.name}")

    def emit(self, event: DialogueEvent) -> None:
        """
        Emit an event to all subscribers.

        Args:
            event: Event to emit
        """
        # Add to history
        self._history.append(event)
        if len(self._history) > self._history_size:
            self._history.pop(0)

        if self._async_mode and self._event_queue:
            # Queue for async processing
            self._event_queue.put(event)
        else:
            # Process synchronously
            self._process_event(event)

    def _process_event(self, event: DialogueEvent) -> None:
        """Process an event by calling all handlers."""
        # Call type-specific handlers
        for handler in self._handlers[event.event_type]:
            try:
                handler(event)
            except Exception as e:
                logger.error(
                    f"Error in event handler for {event.event_type.name}: {e}"
                )

        # Call global handlers
        for handler in self._global_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error in global event handler: {e}")

    def _start_worker(self) -> None:
        """Start the async worker thread."""
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True
        )
        self._worker_thread.start()
        logger.debug("Event bus async worker started")

    def _worker_loop(self) -> None:
        """Worker loop for async event processing."""
        while self._running:
            try:
                event = self._event_queue.get(timeout=1.0)
                self._process_event(event)
            except Exception:
                pass  # Timeout, continue loop

    def stop(self) -> None:
        """Stop the async worker."""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=2.0)
            logger.debug("Event bus async worker stopped")

    def get_history(
        self,
        event_type: Optional[EventType] = None,
        limit: int = 10
    ) -> List[DialogueEvent]:
        """
        Get recent events from history.

        Args:
            event_type: Filter by event type (None for all)
            limit: Maximum number of events to return

        Returns:
            List of recent events (most recent last)
        """
        events = self._history

        if event_type:
            events = [e for e in events if e.event_type == event_type]

        return events[-limit:]

    def clear_history(self) -> None:
        """Clear event history."""
        self._history.clear()


# === Pre-built Subscribers ===

class MetricsCollector:
    """
    Subscriber that collects metrics from events.

    Metrics collected:
        - Turn count
        - Action distribution
        - Transition distribution
        - Source contribution counts
        - Resolution times
        - Error rates
    """

    def __init__(self):
        self.metrics: Dict[str, Any] = {
            "turn_count": 0,
            "action_counts": {},
            "transition_counts": {},
            "source_contribution_counts": {},
            "total_resolution_time_ms": 0,
            "error_count": 0,
            "state_loop_count": 0,
        }

    def handle_event(self, event: DialogueEvent) -> None:
        """Handle an event and update metrics."""
        if event.event_type == EventType.TURN_STARTED:
            self.metrics["turn_count"] += 1

        elif event.event_type == EventType.SOURCE_CONTRIBUTED:
            source = event.data.get("source_name", "unknown")
            if source not in self.metrics["source_contribution_counts"]:
                self.metrics["source_contribution_counts"][source] = 0
            self.metrics["source_contribution_counts"][source] += 1

        elif event.event_type == EventType.CONFLICT_RESOLVED:
            action = event.data.get("winning_action", "unknown")
            if action not in self.metrics["action_counts"]:
                self.metrics["action_counts"][action] = 0
            self.metrics["action_counts"][action] += 1

            self.metrics["total_resolution_time_ms"] += event.data.get(
                "resolution_time_ms", 0
            )

        elif event.event_type == EventType.STATE_TRANSITIONED:
            from_state = event.data.get("from_state")
            to_state = event.data.get("to_state")

            transition_key = f"{from_state}->{to_state}"
            if transition_key not in self.metrics["transition_counts"]:
                self.metrics["transition_counts"][transition_key] = 0
            self.metrics["transition_counts"][transition_key] += 1

            # Detect state loops
            if from_state == to_state:
                self.metrics["state_loop_count"] += 1

        elif event.event_type == EventType.ERROR_OCCURRED:
            self.metrics["error_count"] += 1

    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics."""
        return dict(self.metrics)

    def reset(self) -> None:
        """Reset all metrics."""
        self.metrics = {
            "turn_count": 0,
            "action_counts": {},
            "transition_counts": {},
            "source_contribution_counts": {},
            "total_resolution_time_ms": 0,
            "error_count": 0,
            "state_loop_count": 0,
        }


class DebugLogger:
    """
    Subscriber that logs detailed debug information.
    """

    def __init__(self, log_level: int = logging.DEBUG):
        self._logger = logging.getLogger("blackboard.debug")
        self._log_level = log_level

    def handle_event(self, event: DialogueEvent) -> None:
        """Log event details."""
        self._logger.log(
            self._log_level,
            f"[Turn {event.turn_number}] {event.event_type.name}: {event.data}"
        )
