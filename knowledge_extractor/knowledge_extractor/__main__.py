#!/usr/bin/env python3
"""
Knowledge Extractor CLI

Generate YAML knowledge bases from unstructured documents.

Usage:
    python -m knowledge_extractor --input docs/ --output kb/
    python -m knowledge_extractor -i data.pdf -o knowledge/
    python -m knowledge_extractor --input chat.txt --output kb/
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

from .cli import KnowledgeExtractorCLI
from .config import Config, LLMConfig, ChunkingConfig, ExtractionConfig, DeduplicationConfig, OutputConfig

console = Console()


def setup_logging(verbose: bool = False):
    """Setup logging with rich handler."""
    level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


def main():
    parser = argparse.ArgumentParser(
        description="Generate YAML knowledge base from unstructured documents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process a directory of documents
  python -m knowledge_extractor --input docs/ --output kb/

  # Process single PDF file
  python -m knowledge_extractor -i manual.pdf -o knowledge/

  # Use custom vLLM endpoint
  python -m knowledge_extractor -i docs/ -o kb/ --llm-url http://localhost:8000/v1

Supported formats:
  - PDF (.pdf)
  - Word (.docx)
  - Text (.txt, .md)
  - Excel (.xlsx, .xls, .csv)
  - Q&A pairs (.tsv, .csv, .json with Q&A structure)
        """,
    )

    # Required arguments
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Input file or directory with source documents",
    )
    parser.add_argument(
        "--output", "-o",
        required=True,
        help="Output directory for YAML files",
    )

    # LLM options
    parser.add_argument(
        "--llm-url",
        default="http://localhost:8000/v1",
        help="vLLM API endpoint (default: http://localhost:8000/v1)",
    )
    parser.add_argument(
        "--llm-model",
        default="Qwen/Qwen3-14B",
        help="LLM model name (default: Qwen/Qwen3-14B)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=1024,
        help="Max tokens for LLM response (default: 1024)",
    )

    # Output options
    parser.add_argument(
        "--company-name",
        help="Company name for _meta.yaml",
    )
    parser.add_argument(
        "--company-description",
        help="Company description for _meta.yaml",
    )

    # Extraction options
    parser.add_argument(
        "--min-keywords",
        type=int,
        default=20,
        help="Minimum keywords per section (default: 20)",
    )
    parser.add_argument(
        "--max-keywords",
        type=int,
        default=50,
        help="Maximum keywords per section (default: 50)",
    )
    parser.add_argument(
        "--dedup-threshold",
        type=float,
        default=0.85,
        help="Similarity threshold for deduplication (default: 0.85)",
    )

    # Runtime options
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and chunk without LLM extraction",
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)

    # Validate paths
    input_path = Path(args.input)
    if not input_path.exists():
        console.print(f"[red]Error: Input path does not exist: {input_path}[/red]")
        sys.exit(1)

    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)

    # Build config
    config = Config(
        llm=LLMConfig(
            base_url=args.llm_url,
            model=args.llm_model,
            max_tokens=args.max_tokens,
        ),
        chunking=ChunkingConfig(),
        extraction=ExtractionConfig(
            min_keywords=args.min_keywords,
            max_keywords=args.max_keywords,
        ),
        deduplication=DeduplicationConfig(
            similarity_threshold=args.dedup_threshold,
        ),
        output=OutputConfig(
            company_name=args.company_name,
            company_description=args.company_description,
        ),
        input_path=input_path,
        output_path=output_path,
        verbose=args.verbose,
        dry_run=args.dry_run,
    )

    # Print header
    console.print()
    console.print("=" * 60)
    console.print("[bold]KNOWLEDGE EXTRACTOR[/bold]")
    console.print("=" * 60)
    console.print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    console.print(f"Input: {input_path}")
    console.print(f"Output: {output_path}")
    console.print(f"LLM: {args.llm_model} @ {args.llm_url}")
    console.print("=" * 60)

    # Run extraction
    cli = KnowledgeExtractorCLI(config)

    try:
        result = cli.run()

        console.print()
        console.print("=" * 60)
        console.print("[bold green]COMPLETED[/bold green]")
        console.print("=" * 60)
        console.print(f"Sections generated: {result.total_sections}")
        console.print(f"Categories: {len(result.categories)}")
        console.print(f"Files written: {len(result.files_written)}")
        console.print(f"Processing time: {result.processing_time_s:.1f}s")

        if result.failed_chunks:
            console.print(f"[yellow]Failed chunks: {len(result.failed_chunks)}[/yellow]")

        if result.quality_report:
            console.print(f"Quality pass rate: {result.quality_report.pass_rate:.1%}")

        console.print("=" * 60)
        console.print(f"Output: {output_path}")
        console.print()

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
