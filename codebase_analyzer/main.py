"""CLI entry point for Codebase Analyzer."""

import asyncio
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .analyzer.cache import AnalysisCache
from .analyzer.models import AnalysisResult
from .analyzer.pipeline import AnalysisPipeline
from .config import AppConfig, load_config
from .generator import GeneratorConfig, MarkdownGenerator
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
    result = indexer.index(path)

    # Save index
    index_path = indexer.save_index(index_result=result)

    # Print summary
    _print_index_summary(result.stats, index_path)


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
        typer.Option("--output", "-o", help="Output path for analysis results"),
    ] = None,
    incremental: Annotated[
        bool,
        typer.Option("--incremental", "-i", help="Use incremental analysis with caching"),
    ] = True,
    model: Annotated[
        str,
        typer.Option("--model", "-m", help="LLM model name"),
    ] = "qwen3:14b",
    api_base: Annotated[
        str,
        typer.Option("--api-base", help="LLM API base URL"),
    ] = "http://localhost:11434/v1",
    max_concurrent: Annotated[
        int,
        typer.Option("--concurrent", help="Maximum concurrent LLM requests"),
    ] = 5,
    skip_architecture: Annotated[
        bool,
        typer.Option("--skip-architecture", help="Skip architecture synthesis"),
    ] = False,
    config_file: Annotated[
        Optional[Path],
        typer.Option("--config", "-c", help="Configuration file path"),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-V", help="Enable verbose logging"),
    ] = False,
) -> None:
    """Analyze indexed codebase using LLM.

    This command uses the LLM to analyze the indexed code and generate
    entity summaries, module summaries, and architecture overview.
    """
    # Setup logging
    log_level = "DEBUG" if verbose else "INFO"
    setup_logging(log_level)

    # Load config
    config = load_config(config_file)
    config.index_dir = index_path

    # Determine output path
    output_path = output or (index_path / "analysis.json")

    console.print(
        Panel(
            f"[bold blue]Analyzing codebase from index:[/bold blue] {index_path}\n"
            f"[dim]Model:[/dim] {model}\n"
            f"[dim]API Base:[/dim] {api_base}\n"
            f"[dim]Incremental:[/dim] {incremental}\n"
            f"[dim]Output:[/dim] {output_path}",
            title="Codebase Analyzer",
        )
    )

    # Load index
    indexer = create_indexer(config)
    if not indexer.load_index(index_path):
        console.print("[red]Failed to load index[/red]")
        raise typer.Exit(1)

    # Check if we have a graph
    if indexer.dependency_graph is None:
        console.print("[red]No dependency graph found in index[/red]")
        raise typer.Exit(1)

    # Setup cache for incremental analysis
    cache = None
    if incremental:
        cache_dir = index_path / "cache"
        cache = AnalysisCache(cache_dir=cache_dir, model=model)
        console.print(f"[dim]Using cache at:[/dim] {cache_dir}")

    # Create pipeline
    pipeline = AnalysisPipeline(
        graph=indexer.dependency_graph,
        api_base=api_base,
        model=model,
        config=config,
        cache=cache,
    )

    # Run analysis
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Analyzing codebase...", total=None)

            if incremental and cache:
                result = asyncio.run(
                    pipeline.analyze_incremental(
                        max_concurrent=max_concurrent,
                        skip_architecture=skip_architecture,
                    )
                )
            else:
                result = asyncio.run(
                    pipeline.analyze(
                        max_concurrent=max_concurrent,
                        skip_architecture=skip_architecture,
                    )
                )

            progress.update(task, completed=True, description="Analysis complete")

        # Save results
        result.save(output_path)

        # Print summary
        _print_analysis_summary(result, output_path)

    except Exception as e:
        console.print(f"[red]Analysis failed: {e}[/red]")
        raise typer.Exit(1)
    finally:
        asyncio.run(pipeline.close())


@app.command()
def generate(
    analysis_path: Annotated[
        Path,
        typer.Argument(
            help="Path to the analysis results (JSON file or directory containing analysis.json)",
            exists=True,
            resolve_path=True,
        ),
    ],
    output: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="Output directory for documentation"),
    ] = None,
    title: Annotated[
        str,
        typer.Option("--title", "-t", help="Documentation title"),
    ] = "Project Documentation",
    no_modules: Annotated[
        bool,
        typer.Option("--no-modules", help="Skip module documentation"),
    ] = False,
    no_api: Annotated[
        bool,
        typer.Option("--no-api", help="Skip API documentation"),
    ] = False,
    no_structure: Annotated[
        bool,
        typer.Option("--no-structure", help="Skip structure documentation"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-V", help="Enable verbose logging"),
    ] = False,
) -> None:
    """Generate Markdown documentation from analysis results.

    This command generates documentation files from the analysis results.
    """
    # Setup logging
    log_level = "DEBUG" if verbose else "INFO"
    setup_logging(log_level)

    # Determine the analysis file path
    if analysis_path.is_dir():
        analysis_file = analysis_path / "analysis.json"
    else:
        analysis_file = analysis_path

    if not analysis_file.exists():
        console.print(f"[red]Analysis file not found: {analysis_file}[/red]")
        raise typer.Exit(1)

    # Determine output directory
    output_dir = output or Path("./docs")

    console.print(
        Panel(
            f"[bold blue]Generating documentation:[/bold blue]\n"
            f"[dim]Analysis:[/dim] {analysis_file}\n"
            f"[dim]Title:[/dim] {title}\n"
            f"[dim]Output:[/dim] {output_dir}",
            title="Codebase Analyzer",
        )
    )

    # Load analysis results
    try:
        result = AnalysisResult.load(analysis_file)
        console.print(f"[dim]Loaded analysis with {result.total_entities} entities[/dim]")
    except Exception as e:
        console.print(f"[red]Failed to load analysis: {e}[/red]")
        raise typer.Exit(1)

    # Create generator config
    gen_config = GeneratorConfig(
        title=title,
        create_module_docs=not no_modules,
        create_api_docs=not no_api,
        create_structure=not no_structure,
    )

    # Generate documentation
    try:
        generator = MarkdownGenerator(config=gen_config)
        files = generator.generate(result, output_dir)

        # Print summary
        console.print(f"\n[green]Generated {len(files)} documentation files:[/green]")
        for file_path in files:
            console.print(f"  - {file_path.relative_to(output_dir.parent)}")

        console.print(f"\n[bold green]Documentation generated at: {output_dir}[/bold green]")

    except Exception as e:
        console.print(f"[red]Documentation generation failed: {e}[/red]")
        raise typer.Exit(1)


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


def _print_analysis_summary(result: AnalysisResult, output_path: Path) -> None:
    """Print a summary of the analysis results."""
    table = Table(title="Analysis Summary")

    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Total Entities", f"{result.total_entities:,}")
    table.add_row("Total Modules", f"{result.total_modules:,}")
    table.add_row("Processing Levels", f"{len(result.processing_levels):,}")
    table.add_row("Input Tokens", f"{result.total_tokens_in:,}")
    table.add_row("Output Tokens", f"{result.total_tokens_out:,}")
    table.add_row("Processing Time", f"{result.processing_time_seconds:.1f}s")
    table.add_row("Model", result.model_used)

    console.print(table)

    # Show architecture overview if available
    if result.architecture and result.architecture.overview:
        console.print("\n[bold]Architecture Overview:[/bold]")
        console.print(result.architecture.overview[:500])
        if len(result.architecture.overview) > 500:
            console.print("...")

    console.print(f"\n[green]Analysis saved to: {output_path}[/green]")


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
