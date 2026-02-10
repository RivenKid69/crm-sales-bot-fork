# tests/test_blackboard_event_bus.py

"""
Tests for Blackboard Stage 9: DialogueEventBus.

These tests verify:
1. EventType enum - all event types defined
2. DialogueEvent and specialized events - creation, serialization
3. DialogueEventBus - subscribe, emit, history, async mode
4. MetricsCollector - metrics collection from events
5. DebugLogger - logging functionality
"""

import pytest
import time
import logging
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

from src.blackboard.event_bus import (
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

class TestEventType:
    """Test suite for EventType enum."""

    def test_all_event_types_defined(self):
        """All required event types should be defined."""
        assert EventType.TURN_STARTED is not None
        assert EventType.SOURCE_CONTRIBUTED is not None
        assert EventType.PROPOSAL_VALIDATED is not None
        assert EventType.CONFLICT_RESOLVED is not None
        assert EventType.DECISION_COMMITTED is not None
        assert EventType.STATE_TRANSITIONED is not None
        assert EventType.ERROR_OCCURRED is not None

    def test_event_types_are_unique(self):
        """Each event type should have a unique value."""
        values = [e.value for e in EventType]
        assert len(values) == len(set(values))

    def test_event_types_count(self):
        """Should have exactly 7 event types."""
        assert len(EventType) == 7

class TestDialogueEvent:
    """Test suite for DialogueEvent base class."""

    def test_create_basic_event(self):
        """DialogueEvent should be created with required fields."""
        event = DialogueEvent(
            event_type=EventType.TURN_STARTED,
            turn_number=1,
        )

        assert event.event_type == EventType.TURN_STARTED
        assert event.turn_number == 1
        assert isinstance(event.timestamp, datetime)
        assert event.data == {}

    def test_create_event_with_data(self):
        """DialogueEvent should accept custom data."""
        event = DialogueEvent(
            event_type=EventType.ERROR_OCCURRED,
            turn_number=5,
            data={"error": "test error", "code": 500},
        )

        assert event.data["error"] == "test error"
        assert event.data["code"] == 500

    def test_to_dict_serialization(self):
        """to_dict should serialize event correctly."""
        event = DialogueEvent(
            event_type=EventType.TURN_STARTED,
            turn_number=3,
            data={"intent": "greeting"},
        )

        result = event.to_dict()

        assert result["event_type"] == "TURN_STARTED"
        assert result["turn_number"] == 3
        assert result["data"]["intent"] == "greeting"
        assert "timestamp" in result

    def test_timestamp_format_in_to_dict(self):
        """to_dict should serialize timestamp as ISO format."""
        event = DialogueEvent(event_type=EventType.TURN_STARTED)

        result = event.to_dict()

        # Should be valid ISO format
        datetime.fromisoformat(result["timestamp"])

class TestTurnStartedEvent:
    """Test suite for TurnStartedEvent."""

    def test_create_turn_started_event(self):
        """TurnStartedEvent should be created with required fields."""
        event = TurnStartedEvent(
            turn_number=1,
            intent="greeting",
            state="initial",
        )

        assert event.event_type == EventType.TURN_STARTED
        assert event.turn_number == 1
        assert event.data["intent"] == "greeting"
        assert event.data["state"] == "initial"

    def test_turn_started_with_extra_kwargs(self):
        """TurnStartedEvent should accept additional kwargs."""
        event = TurnStartedEvent(
            turn_number=2,
            intent="buy",
            state="negotiation",
            user_id="user123",
            session_id="sess456",
        )

        assert event.data["user_id"] == "user123"
        assert event.data["session_id"] == "sess456"

class TestSourceContributedEvent:
    """Test suite for SourceContributedEvent."""

    def test_create_source_contributed_event(self):
        """SourceContributedEvent should be created with required fields."""
        event = SourceContributedEvent(
            turn_number=1,
            source_name="IntentProcessor",
            proposals_count=2,
            proposals_summary=["action:ask_question", "transition:negotiation"],
            execution_time_ms=15.5,
        )

        assert event.event_type == EventType.SOURCE_CONTRIBUTED
        assert event.data["source_name"] == "IntentProcessor"
        assert event.data["proposals_count"] == 2
        assert len(event.data["proposals_summary"]) == 2
        assert event.data["execution_time_ms"] == 15.5

    def test_source_contributed_with_extra_kwargs(self):
        """SourceContributedEvent should accept additional kwargs."""
        event = SourceContributedEvent(
            turn_number=1,
            source_name="TestSource",
            proposals_count=1,
            proposals_summary=["test"],
            execution_time_ms=5.0,
            priority="HIGH",
        )

        assert event.data["priority"] == "HIGH"

class TestProposalValidatedEvent:
    """Test suite for ProposalValidatedEvent."""

    def test_create_proposal_validated_event(self):
        """ProposalValidatedEvent should be created with required fields."""
        event = ProposalValidatedEvent(
            turn_number=1,
            valid_count=5,
            error_count=1,
            warning_count=2,
            errors=["Invalid action: unknown"],
        )

        assert event.event_type == EventType.PROPOSAL_VALIDATED
        assert event.data["valid_count"] == 5
        assert event.data["error_count"] == 1
        assert event.data["warning_count"] == 2
        assert event.data["errors"] == ["Invalid action: unknown"]

    def test_proposal_validated_with_no_errors(self):
        """ProposalValidatedEvent should work with empty errors list."""
        event = ProposalValidatedEvent(
            turn_number=1,
            valid_count=10,
            error_count=0,
            warning_count=0,
            errors=[],
        )

        assert event.data["errors"] == []

class TestConflictResolvedEvent:
    """Test suite for ConflictResolvedEvent."""

    def test_create_conflict_resolved_event(self):
        """ConflictResolvedEvent should be created with required fields."""
        event = ConflictResolvedEvent(
            turn_number=1,
            winning_action="ask_question",
            winning_transition="negotiation",
            rejected_count=3,
            merge_decision="merged",
            resolution_time_ms=25.0,
        )

        assert event.event_type == EventType.CONFLICT_RESOLVED
        assert event.data["winning_action"] == "ask_question"
        assert event.data["winning_transition"] == "negotiation"
        assert event.data["rejected_count"] == 3
        assert event.data["merge_decision"] == "merged"
        assert event.data["resolution_time_ms"] == 25.0

    def test_conflict_resolved_with_none_transition(self):
        """ConflictResolvedEvent should allow None transition."""
        event = ConflictResolvedEvent(
            turn_number=1,
            winning_action="continue",
            winning_transition=None,
            rejected_count=0,
            merge_decision="single",
            resolution_time_ms=5.0,
        )

        assert event.data["winning_transition"] is None

class TestDecisionCommittedEvent:
    """Test suite for DecisionCommittedEvent."""

    def test_create_decision_committed_event(self):
        """DecisionCommittedEvent should be created with required fields."""
        event = DecisionCommittedEvent(
            turn_number=1,
            action="ask_question",
            next_state="qualification",
            reason_codes=["intent_match", "state_valid"],
        )

        assert event.event_type == EventType.DECISION_COMMITTED
        assert event.data["action"] == "ask_question"
        assert event.data["next_state"] == "qualification"
        assert event.data["reason_codes"] == ["intent_match", "state_valid"]

class TestStateTransitionedEvent:
    """Test suite for StateTransitionedEvent."""

    def test_create_state_transitioned_event(self):
        """StateTransitionedEvent should be created with required fields."""
        event = StateTransitionedEvent(
            turn_number=1,
            from_state="initial",
            to_state="qualification",
            trigger_reason="intent_buy",
        )

        assert event.event_type == EventType.STATE_TRANSITIONED
        assert event.data["from_state"] == "initial"
        assert event.data["to_state"] == "qualification"
        assert event.data["trigger_reason"] == "intent_buy"

class TestErrorOccurredEvent:
    """Test suite for ErrorOccurredEvent."""

    def test_create_error_occurred_event(self):
        """ErrorOccurredEvent should be created with required fields."""
        event = ErrorOccurredEvent(
            turn_number=1,
            error_type="ValidationError",
            error_message="Invalid proposal format",
            component="ProposalValidator",
        )

        assert event.event_type == EventType.ERROR_OCCURRED
        assert event.data["error_type"] == "ValidationError"
        assert event.data["error_message"] == "Invalid proposal format"
        assert event.data["component"] == "ProposalValidator"

class TestDialogueEventBus:
    """Test suite for DialogueEventBus."""

    @pytest.fixture
    def event_bus(self):
        """Create a fresh event bus for each test."""
        bus = DialogueEventBus()
        yield bus
        bus.stop()

    def test_create_event_bus_default(self):
        """DialogueEventBus should be created with defaults."""
        bus = DialogueEventBus()

        assert bus._async_mode is False
        assert bus._history_size == 100
        assert len(bus._history) == 0

        bus.stop()

    def test_create_event_bus_with_custom_history_size(self):
        """DialogueEventBus should accept custom history size."""
        bus = DialogueEventBus(history_size=50)

        assert bus._history_size == 50

        bus.stop()

    def test_subscribe_to_event_type(self, event_bus):
        """subscribe should register handler for event type."""
        handler = Mock()

        event_bus.subscribe(EventType.TURN_STARTED, handler)

        assert handler in event_bus._handlers[EventType.TURN_STARTED]

    def test_subscribe_multiple_handlers(self, event_bus):
        """Multiple handlers can subscribe to same event type."""
        handler1 = Mock()
        handler2 = Mock()

        event_bus.subscribe(EventType.TURN_STARTED, handler1)
        event_bus.subscribe(EventType.TURN_STARTED, handler2)

        assert handler1 in event_bus._handlers[EventType.TURN_STARTED]
        assert handler2 in event_bus._handlers[EventType.TURN_STARTED]

    def test_subscribe_all(self, event_bus):
        """subscribe_all should register global handler."""
        handler = Mock()

        event_bus.subscribe_all(handler)

        assert handler in event_bus._global_handlers

    def test_unsubscribe_handler(self, event_bus):
        """unsubscribe should remove handler."""
        handler = Mock()
        event_bus.subscribe(EventType.TURN_STARTED, handler)

        event_bus.unsubscribe(EventType.TURN_STARTED, handler)

        assert handler not in event_bus._handlers[EventType.TURN_STARTED]

    def test_unsubscribe_nonexistent_handler(self, event_bus):
        """unsubscribe should not fail for nonexistent handler."""
        handler = Mock()

        # Should not raise
        event_bus.unsubscribe(EventType.TURN_STARTED, handler)

    def test_emit_calls_type_handlers(self, event_bus):
        """emit should call handlers for event type."""
        handler = Mock()
        event_bus.subscribe(EventType.TURN_STARTED, handler)

        event = TurnStartedEvent(turn_number=1, intent="test", state="initial")
        event_bus.emit(event)

        handler.assert_called_once_with(event)

    def test_emit_calls_global_handlers(self, event_bus):
        """emit should call global handlers."""
        handler = Mock()
        event_bus.subscribe_all(handler)

        event = TurnStartedEvent(turn_number=1, intent="test", state="initial")
        event_bus.emit(event)

        handler.assert_called_once_with(event)

    def test_emit_calls_both_type_and_global_handlers(self, event_bus):
        """emit should call both type-specific and global handlers."""
        type_handler = Mock()
        global_handler = Mock()
        event_bus.subscribe(EventType.TURN_STARTED, type_handler)
        event_bus.subscribe_all(global_handler)

        event = TurnStartedEvent(turn_number=1, intent="test", state="initial")
        event_bus.emit(event)

        type_handler.assert_called_once_with(event)
        global_handler.assert_called_once_with(event)

    def test_emit_does_not_call_other_type_handlers(self, event_bus):
        """emit should not call handlers for other event types."""
        handler = Mock()
        event_bus.subscribe(EventType.ERROR_OCCURRED, handler)

        event = TurnStartedEvent(turn_number=1, intent="test", state="initial")
        event_bus.emit(event)

        handler.assert_not_called()

    def test_emit_adds_to_history(self, event_bus):
        """emit should add event to history."""
        event = TurnStartedEvent(turn_number=1, intent="test", state="initial")

        event_bus.emit(event)

        assert len(event_bus._history) == 1
        assert event_bus._history[0] == event

    def test_emit_respects_history_size(self):
        """emit should respect history size limit."""
        bus = DialogueEventBus(history_size=3)

        for i in range(5):
            event = TurnStartedEvent(turn_number=i, intent="test", state="initial")
            bus.emit(event)

        assert len(bus._history) == 3
        # Should keep the most recent events
        assert bus._history[0].turn_number == 2
        assert bus._history[1].turn_number == 3
        assert bus._history[2].turn_number == 4

        bus.stop()

    def test_emit_handles_handler_exception(self, event_bus):
        """emit should continue processing if handler raises."""
        failing_handler = Mock(side_effect=Exception("Handler error"))
        success_handler = Mock()

        event_bus.subscribe(EventType.TURN_STARTED, failing_handler)
        event_bus.subscribe(EventType.TURN_STARTED, success_handler)

        event = TurnStartedEvent(turn_number=1, intent="test", state="initial")
        event_bus.emit(event)

        # Both handlers should be called despite exception
        failing_handler.assert_called_once()
        success_handler.assert_called_once()

    def test_get_history_returns_recent_events(self, event_bus):
        """get_history should return recent events."""
        for i in range(5):
            event = TurnStartedEvent(turn_number=i, intent="test", state="initial")
            event_bus.emit(event)

        history = event_bus.get_history(limit=3)

        assert len(history) == 3
        assert history[0].turn_number == 2
        assert history[1].turn_number == 3
        assert history[2].turn_number == 4

    def test_get_history_filters_by_event_type(self, event_bus):
        """get_history should filter by event type."""
        event_bus.emit(TurnStartedEvent(turn_number=1, intent="test", state="initial"))
        event_bus.emit(ErrorOccurredEvent(
            turn_number=2, error_type="Test", error_message="Test", component="Test"
        ))
        event_bus.emit(TurnStartedEvent(turn_number=3, intent="test", state="initial"))

        history = event_bus.get_history(event_type=EventType.TURN_STARTED)

        assert len(history) == 2
        assert all(e.event_type == EventType.TURN_STARTED for e in history)

    def test_get_history_returns_all_if_fewer_than_limit(self, event_bus):
        """get_history should return all events if fewer than limit."""
        event_bus.emit(TurnStartedEvent(turn_number=1, intent="test", state="initial"))
        event_bus.emit(TurnStartedEvent(turn_number=2, intent="test", state="initial"))

        history = event_bus.get_history(limit=10)

        assert len(history) == 2

    def test_clear_history(self, event_bus):
        """clear_history should remove all events."""
        for i in range(5):
            event = TurnStartedEvent(turn_number=i, intent="test", state="initial")
            event_bus.emit(event)

        event_bus.clear_history()

        assert len(event_bus._history) == 0
        assert event_bus.get_history() == []

class TestDialogueEventBusAsync:
    """Test suite for DialogueEventBus async mode."""

    def test_create_async_event_bus(self):
        """DialogueEventBus should start worker in async mode."""
        bus = DialogueEventBus(async_mode=True)

        assert bus._async_mode is True
        assert bus._running is True
        assert bus._worker_thread is not None
        assert bus._worker_thread.is_alive()

        bus.stop()

    def test_async_emit_queues_event(self):
        """emit in async mode should queue event."""
        bus = DialogueEventBus(async_mode=True)

        event = TurnStartedEvent(turn_number=1, intent="test", state="initial")
        bus.emit(event)

        # Event should be in history (added before queuing)
        assert len(bus._history) == 1

        bus.stop()

    def test_async_emit_processes_event(self):
        """emit in async mode should eventually process event."""
        bus = DialogueEventBus(async_mode=True)
        handler = Mock()
        bus.subscribe(EventType.TURN_STARTED, handler)

        event = TurnStartedEvent(turn_number=1, intent="test", state="initial")
        bus.emit(event)

        # Wait for async processing
        time.sleep(0.1)

        handler.assert_called_once_with(event)

        bus.stop()

    def test_stop_terminates_worker(self):
        """stop should terminate worker thread."""
        bus = DialogueEventBus(async_mode=True)
        thread = bus._worker_thread

        bus.stop()

        assert bus._running is False
        # Thread should terminate (may need short wait)
        thread.join(timeout=3.0)
        assert not thread.is_alive()

class TestMetricsCollector:
    """Test suite for MetricsCollector."""

    @pytest.fixture
    def collector(self):
        """Create a fresh MetricsCollector for each test."""
        return MetricsCollector()

    def test_initial_metrics(self, collector):
        """MetricsCollector should have zero initial metrics."""
        metrics = collector.get_metrics()

        assert metrics["turn_count"] == 0
        assert metrics["action_counts"] == {}
        assert metrics["transition_counts"] == {}
        assert metrics["source_contribution_counts"] == {}
        assert metrics["total_resolution_time_ms"] == 0
        assert metrics["error_count"] == 0
        assert metrics["state_loop_count"] == 0

    def test_handle_turn_started_increments_count(self, collector):
        """handle_event should increment turn_count for TURN_STARTED."""
        event = TurnStartedEvent(turn_number=1, intent="test", state="initial")

        collector.handle_event(event)

        assert collector.metrics["turn_count"] == 1

    def test_handle_source_contributed_tracks_source(self, collector):
        """handle_event should track source contributions."""
        event = SourceContributedEvent(
            turn_number=1,
            source_name="IntentProcessor",
            proposals_count=2,
            proposals_summary=[],
            execution_time_ms=10.0,
        )

        collector.handle_event(event)

        assert collector.metrics["source_contribution_counts"]["IntentProcessor"] == 1

    def test_handle_source_contributed_increments_count(self, collector):
        """handle_event should increment source contribution count."""
        for _ in range(3):
            event = SourceContributedEvent(
                turn_number=1,
                source_name="TestSource",
                proposals_count=1,
                proposals_summary=[],
                execution_time_ms=5.0,
            )
            collector.handle_event(event)

        assert collector.metrics["source_contribution_counts"]["TestSource"] == 3

    def test_handle_conflict_resolved_tracks_action(self, collector):
        """handle_event should track winning actions."""
        event = ConflictResolvedEvent(
            turn_number=1,
            winning_action="ask_question",
            winning_transition=None,
            rejected_count=0,
            merge_decision="single",
            resolution_time_ms=15.0,
        )

        collector.handle_event(event)

        assert collector.metrics["action_counts"]["ask_question"] == 1
        assert collector.metrics["total_resolution_time_ms"] == 15.0

    def test_handle_conflict_resolved_accumulates_time(self, collector):
        """handle_event should accumulate resolution times."""
        for i in range(3):
            event = ConflictResolvedEvent(
                turn_number=i,
                winning_action="action",
                winning_transition=None,
                rejected_count=0,
                merge_decision="single",
                resolution_time_ms=10.0,
            )
            collector.handle_event(event)

        assert collector.metrics["total_resolution_time_ms"] == 30.0

    def test_handle_state_transitioned_tracks_transition(self, collector):
        """handle_event should track state transitions."""
        event = StateTransitionedEvent(
            turn_number=1,
            from_state="initial",
            to_state="qualification",
            trigger_reason="intent",
        )

        collector.handle_event(event)

        assert collector.metrics["transition_counts"]["initial->qualification"] == 1

    def test_handle_state_transitioned_detects_loop(self, collector):
        """handle_event should detect state loops."""
        event = StateTransitionedEvent(
            turn_number=1,
            from_state="qualification",
            to_state="qualification",
            trigger_reason="stuck",
        )

        collector.handle_event(event)

        assert collector.metrics["state_loop_count"] == 1
        assert collector.metrics["transition_counts"]["qualification->qualification"] == 1

    def test_handle_error_occurred_increments_count(self, collector):
        """handle_event should increment error count."""
        event = ErrorOccurredEvent(
            turn_number=1,
            error_type="Test",
            error_message="Test error",
            component="TestComponent",
        )

        collector.handle_event(event)

        assert collector.metrics["error_count"] == 1

    def test_reset_clears_metrics(self, collector):
        """reset should clear all metrics."""
        # Populate metrics
        collector.handle_event(TurnStartedEvent(
            turn_number=1, intent="test", state="initial"
        ))
        collector.handle_event(ErrorOccurredEvent(
            turn_number=1, error_type="Test", error_message="Test", component="Test"
        ))

        collector.reset()

        metrics = collector.get_metrics()
        assert metrics["turn_count"] == 0
        assert metrics["error_count"] == 0

    def test_get_metrics_returns_copy(self, collector):
        """get_metrics should return a copy of metrics."""
        metrics1 = collector.get_metrics()
        metrics1["turn_count"] = 999

        metrics2 = collector.get_metrics()
        assert metrics2["turn_count"] == 0

class TestDebugLogger:
    """Test suite for DebugLogger."""

    def test_create_debug_logger_default(self):
        """DebugLogger should be created with default log level."""
        debug_logger = DebugLogger()

        assert debug_logger._log_level == logging.DEBUG

    def test_create_debug_logger_custom_level(self):
        """DebugLogger should accept custom log level."""
        debug_logger = DebugLogger(log_level=logging.INFO)

        assert debug_logger._log_level == logging.INFO

    def test_handle_event_logs_message(self):
        """handle_event should log event details."""
        debug_logger = DebugLogger()

        with patch.object(debug_logger._logger, 'log') as mock_log:
            event = TurnStartedEvent(turn_number=5, intent="test", state="initial")
            debug_logger.handle_event(event)

            mock_log.assert_called_once()
            call_args = mock_log.call_args
            assert call_args[0][0] == logging.DEBUG
            assert "[Turn 5]" in call_args[0][1]
            assert "TURN_STARTED" in call_args[0][1]

class TestEventBusIntegration:
    """Integration tests for event bus with multiple components."""

    def test_metrics_collector_with_event_bus(self):
        """MetricsCollector should work as event bus subscriber."""
        bus = DialogueEventBus()
        collector = MetricsCollector()

        bus.subscribe_all(collector.handle_event)

        # Emit various events
        bus.emit(TurnStartedEvent(turn_number=1, intent="buy", state="initial"))
        bus.emit(SourceContributedEvent(
            turn_number=1,
            source_name="IntentProcessor",
            proposals_count=2,
            proposals_summary=["action1", "action2"],
            execution_time_ms=10.0,
        ))
        bus.emit(ConflictResolvedEvent(
            turn_number=1,
            winning_action="ask_question",
            winning_transition="qualification",
            rejected_count=1,
            merge_decision="priority",
            resolution_time_ms=5.0,
        ))
        bus.emit(StateTransitionedEvent(
            turn_number=1,
            from_state="initial",
            to_state="qualification",
            trigger_reason="intent_buy",
        ))

        metrics = collector.get_metrics()

        assert metrics["turn_count"] == 1
        assert metrics["source_contribution_counts"]["IntentProcessor"] == 1
        assert metrics["action_counts"]["ask_question"] == 1
        assert metrics["transition_counts"]["initial->qualification"] == 1
        assert metrics["total_resolution_time_ms"] == 5.0

        bus.stop()

    def test_multiple_subscribers(self):
        """Multiple subscribers should receive all events."""
        bus = DialogueEventBus()
        collector1 = MetricsCollector()
        collector2 = MetricsCollector()

        bus.subscribe_all(collector1.handle_event)
        bus.subscribe_all(collector2.handle_event)

        bus.emit(TurnStartedEvent(turn_number=1, intent="test", state="initial"))

        assert collector1.metrics["turn_count"] == 1
        assert collector2.metrics["turn_count"] == 1

        bus.stop()

    def test_selective_subscription(self):
        """Handlers should only receive subscribed event types."""
        bus = DialogueEventBus()
        turn_events = []
        error_events = []

        bus.subscribe(EventType.TURN_STARTED, lambda e: turn_events.append(e))
        bus.subscribe(EventType.ERROR_OCCURRED, lambda e: error_events.append(e))

        bus.emit(TurnStartedEvent(turn_number=1, intent="test", state="initial"))
        bus.emit(ErrorOccurredEvent(
            turn_number=1, error_type="Test", error_message="Test", component="Test"
        ))
        bus.emit(TurnStartedEvent(turn_number=2, intent="test", state="initial"))

        assert len(turn_events) == 2
        assert len(error_events) == 1

        bus.stop()

    def test_event_serialization_roundtrip(self):
        """Events should be serializable to dict."""
        events = [
            TurnStartedEvent(turn_number=1, intent="buy", state="initial"),
            SourceContributedEvent(
                turn_number=1,
                source_name="Test",
                proposals_count=1,
                proposals_summary=["test"],
                execution_time_ms=5.0,
            ),
            ProposalValidatedEvent(
                turn_number=1,
                valid_count=1,
                error_count=0,
                warning_count=0,
                errors=[],
            ),
            ConflictResolvedEvent(
                turn_number=1,
                winning_action="test",
                winning_transition=None,
                rejected_count=0,
                merge_decision="single",
                resolution_time_ms=1.0,
            ),
            DecisionCommittedEvent(
                turn_number=1,
                action="test",
                next_state="next",
                reason_codes=["code1"],
            ),
            StateTransitionedEvent(
                turn_number=1,
                from_state="state1",
                to_state="state2",
                trigger_reason="reason",
            ),
            ErrorOccurredEvent(
                turn_number=1,
                error_type="Error",
                error_message="Message",
                component="Component",
            ),
        ]

        for event in events:
            data = event.to_dict()
            assert isinstance(data, dict)
            assert "event_type" in data
            assert "timestamp" in data
            assert "turn_number" in data
            assert "data" in data

    def test_high_throughput_sync_mode(self):
        """Event bus should handle high throughput in sync mode."""
        bus = DialogueEventBus(history_size=1000)
        counter = {"count": 0}

        def counting_handler(event):
            counter["count"] += 1

        bus.subscribe_all(counting_handler)

        # Emit 1000 events
        for i in range(1000):
            bus.emit(TurnStartedEvent(turn_number=i, intent="test", state="initial"))

        assert counter["count"] == 1000
        assert len(bus._history) == 1000

        bus.stop()
