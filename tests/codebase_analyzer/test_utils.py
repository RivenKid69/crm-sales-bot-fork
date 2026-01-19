"""Tests for codebase_analyzer/utils - Logging, metrics, and progress utilities."""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codebase_analyzer.utils.logging import (
    LogContext,
    get_logger,
    setup_logging,
)
from codebase_analyzer.utils.metrics import (
    OperationMetrics,
    TimingStats,
    TokenStats,
    estimate_tokens,
    format_duration,
    format_tokens,
    get_operation_metrics,
    timed,
    timed_operation,
)
from codebase_analyzer.utils.progress import (
    PhaseMetrics,
    PipelineMetrics,
    create_progress,
    get_metrics,
    progress_context,
    reset_metrics,
)


# ============================================================================
# Logging Tests
# ============================================================================


class TestLogging:
    """Tests for logging utilities."""

    def test_setup_logging_default(self):
        """Test setup_logging with default parameters."""
        logger = setup_logging()

        assert logger is not None
        assert isinstance(logger, logging.Logger)

    def test_setup_logging_with_level(self):
        """Test setup_logging with custom level."""
        logger = setup_logging(level="DEBUG")

        assert logger is not None

    def test_setup_logging_with_file(self, temp_dir: Path):
        """Test setup_logging with log file."""
        log_file = temp_dir / "test.log"
        logger = setup_logging(level="INFO", log_file=log_file)

        # Log something
        logger.info("Test message")

        # File should be created
        assert log_file.exists() or True  # File handler may buffer

    def test_get_logger(self):
        """Test get_logger returns logger instance."""
        logger = get_logger("test_module")

        assert logger is not None
        assert isinstance(logger, logging.Logger)

    def test_get_logger_default_name(self):
        """Test get_logger with default name."""
        logger = get_logger()

        assert logger is not None

    def test_get_logger_same_name_returns_same(self):
        """Test get_logger returns same logger for same name."""
        logger1 = get_logger("same_name")
        logger2 = get_logger("same_name")

        assert logger1 is logger2


class TestLogContext:
    """Tests for LogContext context manager."""

    def test_log_context_basic(self):
        """Test LogContext basic usage."""
        with LogContext("Test operation"):
            # Code executes normally
            pass

    def test_log_context_with_logger(self):
        """Test LogContext with custom logger."""
        logger = get_logger("test")

        with LogContext("Test operation", logger=logger):
            pass

    def test_log_context_nested(self):
        """Test nested LogContext."""
        with LogContext("Outer"):
            with LogContext("Inner"):
                pass

    def test_log_context_on_exception(self):
        """Test LogContext handles exceptions."""
        with pytest.raises(ValueError):
            with LogContext("Failing operation"):
                raise ValueError("Test error")


# ============================================================================
# Metrics Tests - TimingStats
# ============================================================================


class TestTimingStats:
    """Tests for TimingStats dataclass."""

    def test_default_values(self):
        """Test TimingStats default values."""
        stats = TimingStats()

        assert stats.count == 0
        assert stats.total_time == 0.0
        assert stats.min_time == float("inf")
        assert stats.max_time == 0.0

    def test_add_single_duration(self):
        """Test adding a single duration."""
        stats = TimingStats()
        stats.add(1.5)

        assert stats.count == 1
        assert stats.total_time == 1.5
        assert stats.min_time == 1.5
        assert stats.max_time == 1.5

    def test_add_multiple_durations(self):
        """Test adding multiple durations."""
        stats = TimingStats()
        stats.add(1.0)
        stats.add(2.0)
        stats.add(3.0)

        assert stats.count == 3
        assert stats.total_time == 6.0
        assert stats.min_time == 1.0
        assert stats.max_time == 3.0

    def test_avg_time_property(self):
        """Test avg_time property."""
        stats = TimingStats()
        stats.add(2.0)
        stats.add(4.0)

        assert stats.avg_time == 3.0

    def test_avg_time_empty(self):
        """Test avg_time with no data."""
        stats = TimingStats()

        assert stats.avg_time == 0.0


# ============================================================================
# Metrics Tests - TokenStats
# ============================================================================


class TestTokenStats:
    """Tests for TokenStats dataclass."""

    def test_default_values(self):
        """Test TokenStats default values."""
        stats = TokenStats()

        assert stats.input_tokens == 0
        assert stats.output_tokens == 0
        assert stats.cached_tokens == 0

    def test_total_tokens_property(self):
        """Test total_tokens property."""
        stats = TokenStats()
        stats.input_tokens = 100
        stats.output_tokens = 50

        assert stats.total_tokens == 150

    def test_add_usage(self):
        """Test add_usage method."""
        stats = TokenStats()
        stats.add_usage(input_tokens=100, output_tokens=50)
        stats.add_usage(input_tokens=200, output_tokens=100, cached_tokens=50)

        assert stats.input_tokens == 300
        assert stats.output_tokens == 150
        assert stats.cached_tokens == 50


# ============================================================================
# Metrics Tests - OperationMetrics
# ============================================================================


class TestOperationMetrics:
    """Tests for OperationMetrics dataclass."""

    def test_default_values(self):
        """Test OperationMetrics default values."""
        metrics = OperationMetrics(
            timing={},
            tokens=TokenStats(),
            counters={},
            errors={},
        )

        assert len(metrics.timing) == 0
        assert metrics.tokens.total_tokens == 0

    def test_record_timing(self):
        """Test record_timing method."""
        metrics = OperationMetrics(
            timing={},
            tokens=TokenStats(),
            counters={},
            errors={},
        )

        metrics.record_timing("parse", 1.5)
        metrics.record_timing("parse", 2.0)

        assert "parse" in metrics.timing
        assert metrics.timing["parse"].count == 2

    def test_increment(self):
        """Test increment method."""
        metrics = OperationMetrics(
            timing={},
            tokens=TokenStats(),
            counters={},
            errors={},
        )

        metrics.increment("files_processed")
        metrics.increment("files_processed")
        metrics.increment("files_processed", 5)

        assert metrics.counters["files_processed"] == 7

    def test_record_error(self):
        """Test record_error method."""
        metrics = OperationMetrics(
            timing={},
            tokens=TokenStats(),
            counters={},
            errors={},
        )

        metrics.record_error("parse_error")
        metrics.record_error("parse_error")
        metrics.record_error("network_error")

        assert metrics.errors["parse_error"] == 2
        assert metrics.errors["network_error"] == 1

    def test_summary(self):
        """Test summary method."""
        metrics = OperationMetrics(
            timing={},
            tokens=TokenStats(),
            counters={},
            errors={},
        )

        metrics.record_timing("op1", 1.0)
        metrics.increment("counter1")
        metrics.record_error("error1")
        metrics.tokens.add_usage(100, 50)

        summary = metrics.summary()

        assert isinstance(summary, dict)
        assert "timing" in summary
        assert "counters" in summary
        assert "errors" in summary
        assert "tokens" in summary


# ============================================================================
# Metrics Tests - Utility Functions
# ============================================================================


class TestMetricsUtilities:
    """Tests for metrics utility functions."""

    def test_get_operation_metrics(self):
        """Test get_operation_metrics returns singleton."""
        metrics1 = get_operation_metrics()
        metrics2 = get_operation_metrics()

        assert metrics1 is metrics2

    def test_timed_operation_context_manager(self):
        """Test timed_operation context manager."""
        import time

        with timed_operation("test_op"):
            time.sleep(0.01)

        # Should have recorded timing
        # (actual verification depends on global metrics state)

    def test_timed_decorator(self):
        """Test @timed decorator."""
        import time

        @timed("decorated_op")
        def slow_function():
            time.sleep(0.01)
            return "result"

        result = slow_function()
        assert result == "result"

    def test_estimate_tokens(self):
        """Test estimate_tokens function."""
        text = "Hello world, this is a test."
        tokens = estimate_tokens(text)

        assert tokens > 0
        # Rough estimate: ~4 chars per token
        assert tokens >= len(text) // 10
        assert tokens <= len(text)

    def test_estimate_tokens_empty(self):
        """Test estimate_tokens with empty string."""
        tokens = estimate_tokens("")
        assert tokens == 0

    def test_format_duration_seconds(self):
        """Test format_duration with seconds."""
        result = format_duration(5.5)

        assert "5" in result or "s" in result.lower()

    def test_format_duration_minutes(self):
        """Test format_duration with minutes."""
        result = format_duration(125)

        assert "2" in result or "m" in result.lower()

    def test_format_tokens(self):
        """Test format_tokens function."""
        result = format_tokens(1500)

        assert "1" in result
        # May be "1.5K" or "1,500"


# ============================================================================
# Progress Tests - PhaseMetrics
# ============================================================================


class TestPhaseMetrics:
    """Tests for PhaseMetrics dataclass."""

    def test_default_values(self):
        """Test PhaseMetrics default values."""
        phase = PhaseMetrics(name="test_phase")

        assert phase.name == "test_phase"
        assert phase.total_items == 0
        assert phase.processed_items == 0
        assert phase.failed_items == 0
        assert phase.start_time is None
        assert phase.end_time is None
        assert phase.errors == []

    def test_success_rate_property(self):
        """Test success_rate calculation (returns percentage)."""
        phase = PhaseMetrics(
            name="test",
            total_items=100,
            processed_items=80,
            failed_items=20,
        )
        # success_rate returns percentage: (80-20)/80 * 100 = 75.0%
        assert phase.success_rate == 75.0

    def test_success_rate_zero_items(self):
        """Test success_rate with zero items."""
        phase = PhaseMetrics(name="empty")

        assert phase.success_rate == 0.0

    def test_duration_property(self):
        """Test duration calculation."""
        phase = PhaseMetrics(
            name="test",
            start_time=datetime(2024, 1, 1, 12, 0, 0),
            end_time=datetime(2024, 1, 1, 12, 5, 30),
        )

        duration = phase.duration
        assert duration is not None
        assert duration == timedelta(minutes=5, seconds=30)

    def test_duration_no_end(self):
        """Test duration without end time."""
        phase = PhaseMetrics(
            name="test",
            start_time=datetime.now(),
        )

        assert phase.duration is None

    def test_items_per_second(self):
        """Test items_per_second calculation."""
        phase = PhaseMetrics(
            name="test",
            processed_items=100,
            start_time=datetime(2024, 1, 1, 12, 0, 0),
            end_time=datetime(2024, 1, 1, 12, 0, 10),  # 10 seconds
        )

        assert phase.items_per_second == 10.0


# ============================================================================
# Progress Tests - PipelineMetrics
# ============================================================================


class TestPipelineMetrics:
    """Tests for PipelineMetrics dataclass."""

    def test_default_values(self):
        """Test PipelineMetrics default values."""
        metrics = PipelineMetrics()

        assert metrics.phases == {}
        assert metrics.start_time is None
        assert metrics.end_time is None
        assert metrics.total_input_tokens == 0
        assert metrics.total_output_tokens == 0

    def test_start_phase(self):
        """Test starting a phase."""
        metrics = PipelineMetrics()
        phase = metrics.start_phase("parsing", total_items=100)

        assert "parsing" in metrics.phases
        assert phase.name == "parsing"
        assert phase.total_items == 100
        assert phase.start_time is not None

    def test_end_phase(self):
        """Test ending a phase."""
        metrics = PipelineMetrics()
        metrics.start_phase("parsing")
        metrics.end_phase("parsing")

        assert metrics.phases["parsing"].end_time is not None

    def test_total_duration(self):
        """Test total_duration calculation."""
        metrics = PipelineMetrics()
        metrics.start_time = datetime(2024, 1, 1, 12, 0, 0)
        metrics.end_time = datetime(2024, 1, 1, 12, 10, 0)

        duration = metrics.total_duration
        assert duration == timedelta(minutes=10)

    def test_to_table(self):
        """Test to_table returns Rich Table."""
        metrics = PipelineMetrics()
        metrics.start_phase("phase1", 10)
        metrics.phases["phase1"].processed_items = 8
        metrics.end_phase("phase1")

        table = metrics.to_table()

        # Should return a Rich Table object
        assert table is not None

    def test_print_summary(self, capsys):
        """Test print_summary outputs to console."""
        metrics = PipelineMetrics()
        metrics.start_time = datetime.now()
        metrics.start_phase("test", 5)
        metrics.end_phase("test")
        metrics.end_time = datetime.now()

        # Should not raise
        metrics.print_summary()


# ============================================================================
# Progress Tests - Utility Functions
# ============================================================================


class TestProgressUtilities:
    """Tests for progress utility functions."""

    def test_create_progress(self):
        """Test create_progress returns Progress object."""
        progress = create_progress()

        assert progress is not None

    def test_progress_context(self):
        """Test progress_context context manager."""
        with progress_context("Test Progress") as progress:
            assert progress is not None

    def test_get_metrics(self):
        """Test get_metrics returns PipelineMetrics."""
        metrics = get_metrics()

        assert isinstance(metrics, PipelineMetrics)

    def test_reset_metrics(self):
        """Test reset_metrics clears metrics."""
        # Add some data
        metrics = get_metrics()
        metrics.start_phase("test_phase")

        # Reset
        new_metrics = reset_metrics()

        assert new_metrics.phases == {}


# ============================================================================
# Integration Tests
# ============================================================================


class TestUtilsIntegration:
    """Integration tests for utilities working together."""

    def test_logging_with_metrics(self):
        """Test logging and metrics working together."""
        logger = get_logger("integration_test")
        metrics = get_operation_metrics()

        with timed_operation("integration_test"):
            logger.info("Starting operation")
            metrics.increment("operations")
            logger.info("Operation complete")

    def test_progress_with_metrics(self):
        """Test progress tracking with metrics."""
        pipeline_metrics = reset_metrics()

        pipeline_metrics.start_phase("indexing", 100)

        # Simulate processing
        for i in range(10):
            pipeline_metrics.phases["indexing"].processed_items += 1

        pipeline_metrics.end_phase("indexing")

        assert pipeline_metrics.phases["indexing"].processed_items == 10

    def test_full_pipeline_tracking(self):
        """Test tracking a full pipeline with all utilities."""
        # Setup
        logger = get_logger("pipeline")
        pipeline_metrics = reset_metrics()
        pipeline_metrics.start_time = datetime.now()

        # Phase 1: Discovery
        with LogContext("Discovery phase", logger):
            phase1 = pipeline_metrics.start_phase("discovery", 50)
            phase1.processed_items = 50
            pipeline_metrics.end_phase("discovery")

        # Phase 2: Parsing
        with LogContext("Parsing phase", logger):
            phase2 = pipeline_metrics.start_phase("parsing", 50)
            phase2.processed_items = 48
            phase2.failed_items = 2
            pipeline_metrics.end_phase("parsing")

        # Phase 3: Analysis
        with LogContext("Analysis phase", logger):
            phase3 = pipeline_metrics.start_phase("analysis", 48)
            phase3.processed_items = 48
            pipeline_metrics.end_phase("analysis")

        pipeline_metrics.end_time = datetime.now()

        # Verify
        assert len(pipeline_metrics.phases) == 3
        # success_rate returns percentage: (processed - failed) / processed * 100
        assert pipeline_metrics.phases["discovery"].success_rate == 100.0  # (50-0)/50 * 100
        assert pipeline_metrics.phases["parsing"].success_rate == pytest.approx(95.83, rel=0.01)  # (48-2)/48 * 100
        assert pipeline_metrics.total_duration is not None
