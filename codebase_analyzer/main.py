"""CLI entry point for Codebase Analyzer."""

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import AppConfig, load_config
from .indexer.indexer import create_indexer
from .utils.logging import setup_logging
from .utils.progress import get_metrics

app = typer.Typer(
    name="codebase-analyzer",
    help="Automated codebase analysis and documentation generation using Qwen3-30B",
    add_completion=False,
)
console = Console()


def version_callback(value: bool) -> None:
    if value:
        console.print("codebase-analyzer version 0.1.0")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", "-v", callback=version_callback, is_eager=True),
    ] = False,
) -> None:
    """Codebase Analyzer - Automated documentation generation."""
    pass


@app.command()
def index(
    path: Annotated[
        Path,
        typer.Argument(
            help="Path to the codebase to index",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ],
    output: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="Output directory for the index"),
    ] = None,
    config_file: Annotated[
        Optional[Path],
        typer.Option("--config", "-c", help="Configuration file path"),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-V", help="Enable verbose logging"),
    ] = False,
) -> None:
    """Index a codebase for analysis.

    This command parses all source files in the codebase, builds a dependency graph,
    and saves the index for later analysis.
    """
    # Setup logging
    log_level = "DEBUG" if verbose else "INFO"
    setup_logging(log_level)

    # Load config
    config = load_config(config_file)
    config.project_root = path

    if output:
        config.index_dir = output

    console.print(
        Panel(
            f"[bold blue]Indexing codebase:[/bold blue] {path}\n"
            f"[dim]Languages:[/dim] {', '.join(config.indexer.languages)}\n"
            f"[dim]Output:[/dim] {config.index_dir}",
            title="Codebase Analyzer",
        )
    )

    # Run indexer
    indexer = create_indexer(config)
    graph, stats = indexer.index(path)

    # Save index
    index_path = indexer.save_index()

    # Print summary
    _print_index_summary(stats, index_path)


@app.command()
def analyze(
    index_path: Annotated[
        Path,
        typer.Argument(
            help="Path to the code index",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ],
    output: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="Output directory for documentation"),
    ] = None,
    doc_type: Annotated[
        str,
        typer.Option("--type", "-t", help="Documentation type: technical, business, or both"),
    ] = "both",
    config_file: Annotated[
        Optional[Path],
        typer.Option("--config", "-c", help="Configuration file path"),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-V", help="Enable verbose logging"),
    ] = False,
) -> None:
    """Analyze indexed codebase and generate documentation.

    This command uses the LLM to analyze the indexed code and generate
    comprehensive documentation.
    """
    # Setup logging
    log_level = "DEBUG" if verbose else "INFO"
    setup_logging(log_level)

    # Load config
    config = load_config(config_file)
    config.index_dir = index_path

    if output:
        config.output_dir = output

    console.print(
        Panel(
            f"[bold blue]Analyzing codebase from index:[/bold blue] {index_path}\n"
            f"[dim]Documentation type:[/dim] {doc_type}\n"
            f"[dim]Output:[/dim] {config.output_dir}",
            title="Codebase Analyzer",
        )
    )

    # Load index
    indexer = create_indexer(config)
    if not indexer.load_index(index_path):
        console.print("[red]Failed to load index[/red]")
        raise typer.Exit(1)

    # TODO: Implement analysis pipeline
    console.print("[yellow]Analysis pipeline not yet implemented[/yellow]")
    console.print("Next steps:")
    console.print("1. Load embedding model (Qodo-Embed-1-1.5B)")
    console.print("2. Build RAG index")
    console.print("3. Analyze code with LLM")
    console.print("4. Generate documentation")


@app.command()
def generate(
    index_path: Annotated[
        Path,
        typer.Argument(
            help="Path to the code index",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ],
    output: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="Output directory for documentation"),
    ] = None,
    doc_type: Annotated[
        str,
        typer.Option(
            "--type",
            "-t",
            help="Documentation type: technical, business",
        ),
    ] = "technical",
    format: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format: markdown, html, both"),
    ] = "markdown",
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-V", help="Enable verbose logging"),
    ] = False,
) -> None:
    """Generate documentation from analyzed codebase.

    This command generates documentation files from the analysis results.
    """
    # Setup logging
    log_level = "DEBUG" if verbose else "INFO"
    setup_logging(log_level)

    console.print(
        Panel(
            f"[bold blue]Generating documentation:[/bold blue]\n"
            f"[dim]Index:[/dim] {index_path}\n"
            f"[dim]Type:[/dim] {doc_type}\n"
            f"[dim]Format:[/dim] {format}",
            title="Codebase Analyzer",
        )
    )

    # TODO: Implement documentation generation
    console.print("[yellow]Documentation generation not yet implemented[/yellow]")


@app.command()
def stats(
    index_path: Annotated[
        Path,
        typer.Argument(
            help="Path to the code index",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ],
) -> None:
    """Display statistics about an indexed codebase."""
    import json

    stats_file = index_path / "stats.json"
    if not stats_file.exists():
        console.print("[red]No statistics found in index[/red]")
        raise typer.Exit(1)

    with open(stats_file) as f:
        stats_data = json.load(f)

    _print_index_summary_from_dict(stats_data, index_path)


@app.command()
def config(
    output: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="Output path for config file"),
    ] = None,
    show: Annotated[
        bool,
        typer.Option("--show", "-s", help="Show current configuration"),
    ] = False,
) -> None:
    """Manage configuration."""
    if show:
        config = load_config()
        console.print(Panel(str(config.model_dump()), title="Current Configuration"))
        return

    if output:
        config = AppConfig()
        config.to_yaml(output)
        console.print(f"[green]Configuration saved to {output}[/green]")
    else:
        console.print("Use --show to display config or --output to save default config")


def _print_index_summary(stats, index_path: Path) -> None:
    """Print a summary of the indexing results."""
    table = Table(title="Indexing Summary")

    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Total Files", f"{stats.total_files:,}")
    table.add_row("Total Lines", f"{stats.total_lines:,}")
    table.add_row("Classes", f"{stats.total_classes:,}")
    table.add_row("Interfaces", f"{stats.total_interfaces:,}")
    table.add_row("Traits", f"{stats.total_traits:,}")
    table.add_row("Functions", f"{stats.total_functions:,}")
    table.add_row("Methods", f"{stats.total_methods:,}")
    table.add_row("Components (React)", f"{stats.total_components:,}")
    table.add_row("Imports", f"{stats.total_imports:,}")
    table.add_row("Relations", f"{stats.total_relations:,}")

    console.print(table)

    # Files by language
    if stats.files_by_language:
        lang_table = Table(title="Files by Language")
        lang_table.add_column("Language", style="cyan")
        lang_table.add_column("Files", justify="right")
        lang_table.add_column("Lines", justify="right")

        for lang, count in sorted(
            stats.files_by_language.items(), key=lambda x: x[1], reverse=True
        ):
            lines = stats.lines_by_language.get(lang, 0)
            lang_table.add_row(lang, f"{count:,}", f"{lines:,}")

        console.print(lang_table)

    console.print(f"\n[green]Index saved to: {index_path}[/green]")


def _print_index_summary_from_dict(stats_data: dict, index_path: Path) -> None:
    """Print a summary from a stats dictionary."""
    table = Table(title=f"Index Statistics: {index_path}")

    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Total Files", f"{stats_data.get('total_files', 0):,}")
    table.add_row("Total Lines", f"{stats_data.get('total_lines', 0):,}")
    table.add_row("Classes", f"{stats_data.get('total_classes', 0):,}")
    table.add_row("Interfaces", f"{stats_data.get('total_interfaces', 0):,}")
    table.add_row("Functions", f"{stats_data.get('total_functions', 0):,}")
    table.add_row("Methods", f"{stats_data.get('total_methods', 0):,}")

    console.print(table)

    # Files by language
    files_by_lang = stats_data.get("files_by_language", {})
    lines_by_lang = stats_data.get("lines_by_language", {})

    if files_by_lang:
        lang_table = Table(title="Files by Language")
        lang_table.add_column("Language", style="cyan")
        lang_table.add_column("Files", justify="right")
        lang_table.add_column("Lines", justify="right")

        for lang, count in sorted(files_by_lang.items(), key=lambda x: x[1], reverse=True):
            lines = lines_by_lang.get(lang, 0)
            lang_table.add_row(lang, f"{count:,}", f"{lines:,}")

        console.print(lang_table)


if __name__ == "__main__":
    app()
