"""CLI interface for SEO Rewriter."""

import asyncio
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .rewriter import Rewriter, RewriteStyle
from .plagiarism import PlagiarismDetector
from .llm import OllamaClient
from .config import settings

app = typer.Typer(
    name="seo-rewriter",
    help="AI-powered SEO text rewriter with plagiarism detection",
    add_completion=False,
)
console = Console()


def run_async(coro):
    """Run async function in sync context."""
    return asyncio.get_event_loop().run_until_complete(coro)


@app.command()
def rewrite(
    text: Optional[str] = typer.Argument(
        None,
        help="Text to rewrite (or use --file)",
    ),
    file: Optional[Path] = typer.Option(
        None,
        "--file",
        "-f",
        help="Read text from file",
        exists=True,
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Write result to file",
    ),
    style: RewriteStyle = typer.Option(
        RewriteStyle.STANDARD,
        "--style",
        "-s",
        help="Rewriting style",
    ),
    keywords: Optional[str] = typer.Option(
        None,
        "--keywords",
        "-k",
        help="SEO keywords (comma-separated)",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        "-m",
        help="Ollama model name",
    ),
    target: float = typer.Option(
        95.0,
        "--target",
        "-t",
        help="Target uniqueness percentage",
        min=50.0,
        max=100.0,
    ),
    attempts: int = typer.Option(
        3,
        "--attempts",
        "-a",
        help="Maximum rewrite attempts",
        min=1,
        max=10,
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Only output rewritten text",
    ),
):
    """Rewrite text to make it unique."""
    # Get input text
    if file:
        input_text = file.read_text(encoding="utf-8")
    elif text:
        input_text = text
    else:
        # Read from stdin if no text provided
        if not sys.stdin.isatty():
            input_text = sys.stdin.read()
        else:
            console.print("[red]Error: Provide text as argument, --file, or via stdin[/red]")
            raise typer.Exit(1)

    if not input_text.strip():
        console.print("[red]Error: Empty input text[/red]")
        raise typer.Exit(1)

    # Parse keywords
    kw_list = None
    if keywords:
        kw_list = [k.strip() for k in keywords.split(",") if k.strip()]

    # Initialize components
    llm = OllamaClient(model=model) if model else OllamaClient()
    rewriter = Rewriter(
        llm_client=llm,
        max_attempts=attempts,
        target_uniqueness=target,
    )

    async def do_rewrite():
        # Check LLM health
        if not await rewriter.check_health():
            console.print(f"[red]Error: Cannot connect to Ollama at {settings.ollama_base_url}[/red]")
            console.print(f"[yellow]Make sure Ollama is running and model '{llm.model}' is available[/yellow]")
            raise typer.Exit(1)

        return await rewriter.rewrite(
            text=input_text,
            style=style,
            keywords=kw_list,
        )

    # Run with progress indicator
    if quiet:
        result = run_async(do_rewrite())
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(description="Rewriting text...", total=None)
            result = run_async(do_rewrite())

    # Output results
    if quiet:
        console.print(result.rewritten_text)
    else:
        # Show detailed report
        status_color = "green" if result.success else "red"
        status_text = "PASSED" if result.success else "FAILED"

        console.print()
        console.print(Panel(
            result.rewritten_text,
            title="Rewritten Text",
            border_style="blue",
        ))

        console.print()

        # Metrics table
        table = Table(title="Plagiarism Analysis")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")

        report = result.plagiarism_report
        table.add_row(
            "Uniqueness",
            f"[{status_color}]{report.uniqueness_score:.1f}%[/{status_color}]"
        )
        table.add_row("Status", f"[{status_color}]{status_text}[/{status_color}]")
        table.add_row("Attempts", str(result.attempts))
        table.add_row("Style", result.style_used.value)
        table.add_row("", "")
        table.add_row("N-gram similarity", f"{report.metrics.ngram_similarity * 100:.1f}%")
        table.add_row("Jaccard similarity", f"{report.metrics.jaccard_similarity * 100:.1f}%")
        table.add_row("SimHash similarity", f"{report.metrics.simhash_similarity * 100:.1f}%")
        table.add_row("Winnowing similarity", f"{report.metrics.winnowing_similarity * 100:.1f}%")
        table.add_row("", "")
        table.add_row("Original words", str(report.original_word_count))
        table.add_row("Rewritten words", str(report.rewritten_word_count))

        console.print(table)

    # Save to file if requested
    if output:
        output.write_text(result.rewritten_text, encoding="utf-8")
        if not quiet:
            console.print(f"\n[green]Saved to {output}[/green]")

    # Exit with error if failed
    if not result.success:
        raise typer.Exit(1)


@app.command()
def check(
    original: str = typer.Argument(
        ...,
        help="Original text or path to file",
    ),
    rewritten: str = typer.Argument(
        ...,
        help="Rewritten text or path to file",
    ),
    threshold: float = typer.Option(
        95.0,
        "--threshold",
        "-t",
        help="Uniqueness threshold percentage",
    ),
):
    """Check similarity between two texts."""
    # Load texts (from file if path exists)
    orig_path = Path(original)
    rewr_path = Path(rewritten)

    orig_text = orig_path.read_text() if orig_path.exists() else original
    rewr_text = rewr_path.read_text() if rewr_path.exists() else rewritten

    # Analyze
    detector = PlagiarismDetector(uniqueness_threshold=threshold / 100)
    report = detector.analyze(orig_text, rewr_text)

    # Display results
    status_color = "green" if report.is_unique else "red"
    status_text = "UNIQUE" if report.is_unique else "PLAGIARIZED"

    console.print()
    console.print(Panel(
        report.summary(),
        title=f"Plagiarism Report [{status_text}]",
        border_style=status_color,
    ))

    if not report.is_unique:
        raise typer.Exit(1)


@app.command()
def models():
    """List available Ollama models."""
    llm = OllamaClient()

    async def list_models():
        try:
            return await llm.list_models()
        except Exception as e:
            console.print(f"[red]Error connecting to Ollama: {e}[/red]")
            raise typer.Exit(1)

    model_list = run_async(list_models())

    if not model_list:
        console.print("[yellow]No models found. Install one with: ollama pull qwen3:8b[/yellow]")
        return

    console.print("\n[bold]Available models:[/bold]")
    for model in model_list:
        marker = " [green](current)[/green]" if model == settings.ollama_model else ""
        console.print(f"  - {model}{marker}")


@app.command()
def config():
    """Show current configuration."""
    table = Table(title="Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value")

    table.add_row("Ollama URL", settings.ollama_base_url)
    table.add_row("Model", settings.ollama_model)
    table.add_row("Timeout", f"{settings.ollama_timeout}s")
    table.add_row("Max attempts", str(settings.max_rewrite_attempts))
    table.add_row("Target uniqueness", f"{settings.target_uniqueness}%")
    table.add_row("N-gram size", str(settings.ngram_size))
    table.add_row("Shingle size", str(settings.shingle_size))

    console.print()
    console.print(table)
    console.print("\n[dim]Override with environment variables (prefix: SEO_)[/dim]")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind"),
):
    """Start REST API server."""
    console.print(f"[green]Starting API server at http://{host}:{port}[/green]")
    console.print("[dim]API docs at /docs, health at /health[/dim]\n")

    from .api import run_server
    run_server(host=host, port=port)


if __name__ == "__main__":
    app()
