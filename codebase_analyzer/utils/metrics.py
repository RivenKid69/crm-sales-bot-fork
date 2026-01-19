"""Performance metrics and statistics tracking."""

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Iterator, TypeVar

from .logging import get_logger

logger = get_logger("metrics")

T = TypeVar("T")


@dataclass
class TimingStats:
    """Statistics for timing measurements."""

    count: int = 0
    total_time: float = 0.0
    min_time: float = float("inf")
    max_time: float = 0.0

    def add(self, duration: float) -> None:
        """Add a timing measurement."""
        self.count += 1
        self.total_time += duration
        self.min_time = min(self.min_time, duration)
        self.max_time = max(self.max_time, duration)

    @property
    def avg_time(self) -> float:
        """Calculate average time."""
        return self.total_time / self.count if self.count > 0 else 0.0


@dataclass
class TokenStats:
    """Statistics for token usage."""

    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def add_usage(
        self, input_tokens: int = 0, output_tokens: int = 0, cached_tokens: int = 0
    ) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cached_tokens += cached_tokens


@dataclass
class OperationMetrics:
    """Comprehensive metrics for operations."""

    timing: dict[str, TimingStats] = field(default_factory=dict)
    tokens: TokenStats = field(default_factory=TokenStats)
    counters: dict[str, int] = field(default_factory=dict)
    errors: dict[str, int] = field(default_factory=dict)

    def record_timing(self, operation: str, duration: float) -> None:
        """Record timing for an operation."""
        if operation not in self.timing:
            self.timing[operation] = TimingStats()
        self.timing[operation].add(duration)

    def increment(self, counter: str, value: int = 1) -> None:
        """Increment a counter."""
        self.counters[counter] = self.counters.get(counter, 0) + value

    def record_error(self, error_type: str) -> None:
        """Record an error occurrence."""
        self.errors[error_type] = self.errors.get(error_type, 0) + 1

    def summary(self) -> dict[str, Any]:
        """Get a summary of all metrics."""
        return {
            "timing": {
                name: {
                    "count": stats.count,
                    "total": stats.total_time,
                    "avg": stats.avg_time,
                    "min": stats.min_time if stats.min_time != float("inf") else 0,
                    "max": stats.max_time,
                }
                for name, stats in self.timing.items()
            },
            "tokens": {
                "input": self.tokens.input_tokens,
                "output": self.tokens.output_tokens,
                "cached": self.tokens.cached_tokens,
                "total": self.tokens.total_tokens,
            },
            "counters": dict(self.counters),
            "errors": dict(self.errors),
        }


# Global metrics instance
_operation_metrics: OperationMetrics | None = None


def get_operation_metrics() -> OperationMetrics:
    """Get or create the global operation metrics instance."""
    global _operation_metrics
    if _operation_metrics is None:
        _operation_metrics = OperationMetrics()
    return _operation_metrics


@contextmanager
def timed_operation(name: str) -> Iterator[None]:
    """Context manager for timing an operation.

    Usage:
        with timed_operation("embedding_generation"):
            # do work
    """
    metrics = get_operation_metrics()
    start = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start
        metrics.record_timing(name, duration)
        logger.debug(f"{name}: {duration:.3f}s")


def timed(name: str | None = None) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator for timing function execution.

    Usage:
        @timed("my_operation")
        def my_function():
            ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        operation_name = name or func.__name__

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            with timed_operation(operation_name):
                return func(*args, **kwargs)

        return wrapper

    return decorator


def estimate_tokens(text: str) -> int:
    """Rough estimate of token count (approximately 4 chars per token for code).

    This is a simple heuristic. For accurate counts, use the actual tokenizer.
    """
    # Code tends to have more tokens per character than natural language
    return len(text) // 3


def format_duration(seconds: float) -> str:
    """Format duration in human-readable format."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def format_tokens(count: int) -> str:
    """Format token count with appropriate suffix."""
    if count < 1000:
        return str(count)
    elif count < 1_000_000:
        return f"{count / 1000:.1f}K"
    else:
        return f"{count / 1_000_000:.1f}M"
