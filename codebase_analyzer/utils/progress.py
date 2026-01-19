"""Progress tracking utilities using Rich."""

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Iterator

from rich.console import Console
from rich.live import Live
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

console = Console()


def create_progress() -> Progress:
    """Create a configured progress bar."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=False,
    )


@contextmanager
def progress_context(description: str = "Processing") -> Iterator[Progress]:
    """Context manager for progress tracking."""
    progress = create_progress()
    with progress:
        yield progress


@dataclass
class PhaseMetrics:
    """Metrics for a single processing phase."""

    name: str
    total_items: int = 0
    processed_items: int = 0
    failed_items: int = 0
    start_time: datetime | None = None
    end_time: datetime | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.processed_items == 0:
            return 0.0
        return ((self.processed_items - self.failed_items) / self.processed_items) * 100

    @property
    def duration(self) -> timedelta | None:
        """Calculate phase duration."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None

    @property
    def items_per_second(self) -> float:
        """Calculate processing speed."""
        if self.duration and self.processed_items > 0:
            return self.processed_items / self.duration.total_seconds()
        return 0.0


@dataclass
class PipelineMetrics:
    """Metrics for the entire analysis pipeline."""

    phases: dict[str, PhaseMetrics] = field(default_factory=dict)
    start_time: datetime | None = None
    end_time: datetime | None = None

    # Token statistics
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    # File statistics
    total_files: int = 0
    total_lines: int = 0
    files_by_language: dict[str, int] = field(default_factory=dict)

    def start_phase(self, name: str, total_items: int = 0) -> PhaseMetrics:
        """Start tracking a new phase."""
        phase = PhaseMetrics(name=name, total_items=total_items, start_time=datetime.now())
        self.phases[name] = phase
        return phase

    def end_phase(self, name: str) -> None:
        """Mark a phase as complete."""
        if name in self.phases:
            self.phases[name].end_time = datetime.now()

    @property
    def total_duration(self) -> timedelta | None:
        """Calculate total pipeline duration."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None

    def to_table(self) -> Table:
        """Generate a Rich table with metrics summary."""
        table = Table(title="Pipeline Metrics", show_header=True)
        table.add_column("Phase", style="cyan")
        table.add_column("Items", justify="right")
        table.add_column("Failed", justify="right", style="red")
        table.add_column("Success %", justify="right")
        table.add_column("Duration", justify="right")
        table.add_column("Speed", justify="right")

        for name, phase in self.phases.items():
            duration_str = str(phase.duration).split(".")[0] if phase.duration else "-"
            speed_str = f"{phase.items_per_second:.1f}/s" if phase.items_per_second > 0 else "-"
            table.add_row(
                name,
                str(phase.processed_items),
                str(phase.failed_items),
                f"{phase.success_rate:.1f}%",
                duration_str,
                speed_str,
            )

        return table

    def print_summary(self) -> None:
        """Print a summary of metrics to console."""
        console.print()
        console.print(self.to_table())
        console.print()

        if self.total_duration:
            console.print(f"[bold]Total duration:[/bold] {str(self.total_duration).split('.')[0]}")

        console.print(f"[bold]Total files:[/bold] {self.total_files:,}")
        console.print(f"[bold]Total lines:[/bold] {self.total_lines:,}")

        if self.total_input_tokens > 0:
            console.print(f"[bold]Input tokens:[/bold] {self.total_input_tokens:,}")
            console.print(f"[bold]Output tokens:[/bold] {self.total_output_tokens:,}")

        if self.files_by_language:
            console.print("\n[bold]Files by language:[/bold]")
            for lang, count in sorted(
                self.files_by_language.items(), key=lambda x: x[1], reverse=True
            ):
                console.print(f"  {lang}: {count:,}")


# Global metrics instance
_metrics: PipelineMetrics | None = None


def get_metrics() -> PipelineMetrics:
    """Get or create the global metrics instance."""
    global _metrics
    if _metrics is None:
        _metrics = PipelineMetrics()
    return _metrics


def reset_metrics() -> PipelineMetrics:
    """Reset and return a new metrics instance."""
    global _metrics
    _metrics = PipelineMetrics()
    _metrics.start_time = datetime.now()
    return _metrics
