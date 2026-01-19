"""Logging configuration for Codebase Analyzer."""

import logging
import sys
from pathlib import Path
from typing import Literal

from rich.console import Console
from rich.logging import RichHandler

# Global console instance
console = Console()


def setup_logging(
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO",
    log_file: Path | None = None,
) -> logging.Logger:
    """Configure logging with Rich handler for terminal output.

    Args:
        level: Logging level
        log_file: Optional file path for log output

    Returns:
        Configured logger instance
    """
    # Create logger
    logger = logging.getLogger("codebase_analyzer")
    logger.setLevel(getattr(logging, level))

    # Clear existing handlers
    logger.handlers.clear()

    # Rich console handler for terminal
    rich_handler = RichHandler(
        console=console,
        show_time=True,
        show_path=False,
        markup=True,
        rich_tracebacks=True,
        tracebacks_show_locals=True,
    )
    rich_handler.setLevel(getattr(logging, level))
    rich_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(rich_handler)

    # File handler if specified
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
            )
        )
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Get a logger instance.

    Args:
        name: Logger name (will be prefixed with 'codebase_analyzer.')

    Returns:
        Logger instance
    """
    if name:
        return logging.getLogger(f"codebase_analyzer.{name}")
    return logging.getLogger("codebase_analyzer")


class LogContext:
    """Context manager for scoped logging with indentation."""

    _indent_level = 0

    def __init__(self, message: str, logger: logging.Logger | None = None):
        self.message = message
        self.logger = logger or get_logger()

    def __enter__(self) -> "LogContext":
        indent = "  " * LogContext._indent_level
        self.logger.info(f"{indent}[bold blue]>>>[/bold blue] {self.message}")
        LogContext._indent_level += 1
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        LogContext._indent_level -= 1
        indent = "  " * LogContext._indent_level
        if exc_type:
            self.logger.error(f"{indent}[bold red]<<<[/bold red] {self.message} [FAILED]")
        else:
            self.logger.info(f"{indent}[bold green]<<<[/bold green] {self.message} [DONE]")
