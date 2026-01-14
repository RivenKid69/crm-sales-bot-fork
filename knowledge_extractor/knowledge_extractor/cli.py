"""CLI implementation with progress tracking."""

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from .chunking import SemanticChunker, QAChunker, TableChunker
from .chunking.base import Chunk
from .config import Config, CATEGORIES
from .deduplication import SemanticDeduplicator
from .extraction import KnowledgeExtractor
from .extraction.schemas import ExtractedSection
from .output import CategoryRouter, MetaGenerator, YAMLWriter
from .parsers import get_parser_for_file
from .parsers.base import ContentType, ParsedDocument
from .validation import QualityChecker

logger = logging.getLogger(__name__)
console = Console()


@dataclass
class ExtractionResult:
    """Final extraction result."""

    total_sections: int
    categories: List[str]
    files_written: List[Path]
    processing_time_s: float
    failed_chunks: List
    quality_report: Optional["QualityReport"] = None


class KnowledgeExtractorCLI:
    """Main CLI class."""

    def __init__(self, config: Config):
        self.config = config
        self.extractor = KnowledgeExtractor(config)
        self.deduplicator = SemanticDeduplicator(
            similarity_threshold=config.deduplication.similarity_threshold,
            embedder_model=config.deduplication.embedder_model,
        )
        self.router = CategoryRouter()
        self.quality_checker = QualityChecker()

    def run(self) -> ExtractionResult:
        """Run full extraction pipeline."""
        start_time = time.time()

        # 1. Parse documents
        console.print("\n[bold blue]1. Parsing documents...[/bold blue]")
        documents = self._parse_documents()
        console.print(f"   Parsed {len(documents)} documents")

        if not documents:
            console.print("[red]No documents found![/red]")
            return ExtractionResult(
                total_sections=0,
                categories=[],
                files_written=[],
                processing_time_s=time.time() - start_time,
                failed_chunks=[],
            )

        # 2. Chunk documents
        console.print("\n[bold blue]2. Chunking documents...[/bold blue]")
        chunks = self._chunk_documents(documents)
        console.print(f"   Created {len(chunks)} chunks")

        if self.config.dry_run:
            console.print("\n[yellow]Dry run mode - stopping before LLM extraction[/yellow]")
            return ExtractionResult(
                total_sections=0,
                categories=[],
                files_written=[],
                processing_time_s=time.time() - start_time,
                failed_chunks=[],
            )

        # 3. Extract sections
        console.print("\n[bold blue]3. Extracting knowledge (LLM)...[/bold blue]")
        sections = self._extract_sections(chunks)
        console.print(f"   Extracted {len(sections)} sections")

        # 4. Deduplicate
        console.print("\n[bold blue]4. Deduplicating...[/bold blue]")
        dedup_result = self.deduplicator.deduplicate(sections)
        sections = dedup_result.kept_sections
        console.print(f"   Kept {len(sections)} sections, removed {dedup_result.removed_count}")

        # 5. Validate
        console.print("\n[bold blue]5. Validating quality...[/bold blue]")
        quality_report = self.quality_checker.check(sections)
        console.print(f"   Pass rate: {quality_report.pass_rate:.1%}")

        # 6. Write output
        console.print("\n[bold blue]6. Writing output...[/bold blue]")
        files_written = self._write_output(sections)
        console.print(f"   Written {len(files_written)} files")

        # Summary
        elapsed = time.time() - start_time
        self._print_summary(sections, quality_report, elapsed)

        return ExtractionResult(
            total_sections=len(sections),
            categories=list(set(s.category for s in sections)),
            files_written=files_written,
            processing_time_s=elapsed,
            failed_chunks=self.extractor.get_failed_chunks(),
            quality_report=quality_report,
        )

    def _parse_documents(self) -> List[ParsedDocument]:
        """Parse all input documents."""
        input_path = Path(self.config.input_path)
        documents = []

        if input_path.is_file():
            files = [input_path]
        else:
            # Recursively find all supported files
            files = []
            for ext in [".pdf", ".docx", ".txt", ".xlsx", ".csv", ".json", ".tsv"]:
                files.extend(input_path.rglob(f"*{ext}"))

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Parsing...", total=len(files))

            for filepath in files:
                try:
                    parser = get_parser_for_file(str(filepath))
                    doc = parser.parse(filepath)
                    if not doc.is_empty:
                        documents.append(doc)
                except Exception as e:
                    logger.warning(f"Failed to parse {filepath}: {e}")

                progress.advance(task)

        return documents

    def _chunk_documents(self, documents: List[ParsedDocument]) -> List[Chunk]:
        """Chunk all documents."""
        chunks = []

        for doc in documents:
            # Select chunker based on content type
            if doc.content_type == ContentType.QA_PAIRS:
                chunker = QAChunker()
            elif doc.content_type == ContentType.TABLE:
                chunker = TableChunker()
            else:
                chunker = SemanticChunker(
                    min_chunk_size=self.config.chunking.min_chunk_size,
                    max_chunk_size=self.config.chunking.max_chunk_size,
                )

            doc_chunks = chunker.chunk(doc)
            chunks.extend(doc_chunks)

        return chunks

    def _extract_sections(self, chunks: List[Chunk]) -> List[ExtractedSection]:
        """Extract sections from chunks using LLM."""
        sections = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Extracting...", total=len(chunks))

            def on_progress(current, total, result):
                progress.update(task, completed=current)
                if result.section:
                    sections.append(result.section)

            list(self.extractor.extract_batch(chunks, on_progress=on_progress))

        return sections

    def _write_output(self, sections: List[ExtractedSection]) -> List[Path]:
        """Write sections to YAML files."""
        output_path = Path(self.config.output_path)
        output_path.mkdir(parents=True, exist_ok=True)

        # Route sections to categories
        sections_by_file = self.router.distribute(sections)

        # Write YAML files
        writer = YAMLWriter(output_path)
        files_written = []

        for filename, file_sections in sections_by_file.items():
            category = filename.replace(".yaml", "")
            filepath = writer.write_category_file(filename, file_sections, category)
            files_written.append(filepath)

        # Write _meta.yaml
        meta_gen = MetaGenerator(output_path)
        meta_path = meta_gen.generate(
            sections,
            company_name=self.config.output.company_name,
            company_description=self.config.output.company_description,
        )
        files_written.append(meta_path)

        return files_written

    def _print_summary(self, sections, quality_report, elapsed):
        """Print summary table."""
        console.print("\n")

        table = Table(title="Extraction Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Total Sections", str(len(sections)))
        table.add_row("Categories", str(len(set(s.category for s in sections))))
        table.add_row("Quality Pass Rate", f"{quality_report.pass_rate:.1%}")
        table.add_row("Issues", str(len(quality_report.issues)))
        table.add_row("Warnings", str(len(quality_report.warnings)))
        table.add_row("Processing Time", f"{elapsed:.1f}s")

        console.print(table)

        # Category breakdown
        cat_table = Table(title="Sections by Category")
        cat_table.add_column("Category")
        cat_table.add_column("Count")

        cat_counts = {}
        for s in sections:
            cat_counts[s.category] = cat_counts.get(s.category, 0) + 1

        for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
            cat_table.add_row(cat, str(count))

        console.print(cat_table)

    def save_checkpoint(self):
        """Save checkpoint for resume (not implemented yet)."""
        pass
