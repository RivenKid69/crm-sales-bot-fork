"""Main indexer module for orchestrating code parsing and indexing."""

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Iterator

from ..config import AppConfig, get_config
from ..utils.logging import LogContext, get_logger
from ..utils.progress import create_progress, get_metrics, reset_metrics
from .graph.dependency_graph import DependencyGraph, build_dependency_graph
from .models.entities import FileEntity, Language
from .models.relations import CodebaseStats
from .parsers.base import get_parser_for_file

logger = get_logger("indexer")


class CodebaseIndexer:
    """Orchestrates indexing of a codebase.

    Responsible for:
    - Discovering source files
    - Parsing files with appropriate parsers
    - Building the dependency graph
    - Generating statistics
    """

    def __init__(self, config: AppConfig | None = None):
        self.config = config or get_config()
        self._file_entities: list[FileEntity] = []
        self._dependency_graph: DependencyGraph | None = None
        self._stats: CodebaseStats | None = None

    def discover_files(self) -> list[Path]:
        """Discover all source files to index.

        Returns:
            List of file paths matching the configured patterns
        """
        files: list[Path] = []
        root = self.config.project_root

        with LogContext("Discovering source files"):
            for pattern in self.config.indexer.include_patterns:
                for file_path in root.glob(pattern):
                    # Check exclusions
                    if self._should_exclude(file_path):
                        continue

                    # Check file size
                    if self._is_file_too_large(file_path):
                        logger.debug(f"Skipping large file: {file_path}")
                        continue

                    files.append(file_path)

            logger.info(f"Discovered {len(files)} source files")

        return files

    def _should_exclude(self, file_path: Path) -> bool:
        """Check if a file should be excluded based on patterns."""
        path_str = str(file_path)
        for pattern in self.config.indexer.exclude_patterns:
            # Simple glob matching
            if "*" in pattern:
                # Convert glob to parts for matching
                pattern_parts = pattern.replace("**", "*").split("*")
                if all(part in path_str for part in pattern_parts if part):
                    return True
            elif pattern in path_str:
                return True
        return False

    def _is_file_too_large(self, file_path: Path) -> bool:
        """Check if a file exceeds the size limit."""
        try:
            size_mb = file_path.stat().st_size / (1024 * 1024)
            return size_mb > self.config.indexer.max_file_size_mb
        except OSError:
            return True

    def parse_files(self, files: list[Path]) -> list[FileEntity]:
        """Parse all source files.

        Args:
            files: List of file paths to parse

        Returns:
            List of parsed file entities
        """
        file_entities: list[FileEntity] = []
        metrics = get_metrics()
        phase = metrics.start_phase("parsing", len(files))

        with LogContext("Parsing source files"):
            progress = create_progress()

            with progress:
                task = progress.add_task("Parsing files", total=len(files))

                # Use parallel processing for large codebases
                if len(files) > 100 and self.config.indexer.parallel_workers > 1:
                    file_entities = self._parse_parallel(files, progress, task)
                else:
                    file_entities = self._parse_sequential(files, progress, task)

            phase.processed_items = len(file_entities)
            phase.failed_items = len(files) - len(file_entities)
            metrics.end_phase("parsing")

            logger.info(f"Successfully parsed {len(file_entities)} files")

        self._file_entities = file_entities
        return file_entities

    def _parse_sequential(
        self,
        files: list[Path],
        progress,
        task,
    ) -> list[FileEntity]:
        """Parse files sequentially."""
        file_entities: list[FileEntity] = []

        for file_path in files:
            entity = self._parse_single_file(file_path)
            if entity:
                file_entities.append(entity)
            progress.advance(task)

        return file_entities

    def _parse_parallel(
        self,
        files: list[Path],
        progress,
        task,
    ) -> list[FileEntity]:
        """Parse files in parallel."""
        file_entities: list[FileEntity] = []

        # Note: ProcessPoolExecutor doesn't work well with tree-sitter
        # So we use sequential parsing but in batches
        # For true parallelism, consider using separate processes

        batch_size = 50
        for i in range(0, len(files), batch_size):
            batch = files[i : i + batch_size]
            for file_path in batch:
                entity = self._parse_single_file(file_path)
                if entity:
                    file_entities.append(entity)
                progress.advance(task)

        return file_entities

    def _parse_single_file(self, file_path: Path) -> FileEntity | None:
        """Parse a single file."""
        try:
            parser = get_parser_for_file(file_path)
            if parser:
                return parser.parse_file(file_path)
            else:
                logger.debug(f"No parser for file: {file_path}")
                return None
        except Exception as e:
            logger.warning(f"Failed to parse {file_path}: {e}")
            return None

    def build_graph(
        self,
        file_entities: list[FileEntity] | None = None,
    ) -> DependencyGraph:
        """Build the dependency graph from parsed entities.

        Args:
            file_entities: Optional list of file entities (uses cached if not provided)

        Returns:
            The dependency graph
        """
        entities = file_entities or self._file_entities

        if not entities:
            raise ValueError("No file entities to build graph from. Run parse_files first.")

        with LogContext("Building dependency graph"):
            self._dependency_graph = build_dependency_graph(entities)

        return self._dependency_graph

    def compute_stats(self) -> CodebaseStats:
        """Compute statistics about the indexed codebase."""
        stats = CodebaseStats()

        for file_entity in self._file_entities:
            stats.total_files += 1
            stats.total_lines += file_entity.line_count

            # Track by language
            lang = file_entity.language.value
            stats.files_by_language[lang] = stats.files_by_language.get(lang, 0) + 1
            stats.lines_by_language[lang] = (
                stats.lines_by_language.get(lang, 0) + file_entity.line_count
            )

            # Count entities
            stats.total_imports += len(file_entity.imports)
            stats.total_functions += len(file_entity.functions)
            stats.total_components += len(file_entity.components)

            for cls in file_entity.classes:
                if cls.is_interface:
                    stats.total_interfaces += 1
                elif cls.is_trait:
                    stats.total_traits += 1
                else:
                    stats.total_classes += 1

                stats.total_methods += len(cls.methods)

        # Add graph stats
        if self._dependency_graph:
            stats.total_relations = self._dependency_graph.stats["total_relations"]

        self._stats = stats
        return stats

    def index(self, project_root: Path | None = None) -> tuple[DependencyGraph, CodebaseStats]:
        """Run the full indexing pipeline.

        Args:
            project_root: Optional project root to override config

        Returns:
            Tuple of (dependency_graph, statistics)
        """
        if project_root:
            self.config.project_root = project_root

        reset_metrics()

        logger.info(f"Starting indexing of {self.config.project_root}")

        # Discover files
        files = self.discover_files()

        if not files:
            logger.warning("No source files found to index")
            return DependencyGraph(), CodebaseStats()

        # Parse files
        file_entities = self.parse_files(files)

        if not file_entities:
            logger.warning("No files were successfully parsed")
            return DependencyGraph(), CodebaseStats()

        # Build graph
        graph = self.build_graph(file_entities)

        # Compute stats
        stats = self.compute_stats()

        # Print summary
        get_metrics().print_summary()

        return graph, stats

    def save_index(self, output_dir: Path | None = None) -> Path:
        """Save the index to disk.

        Args:
            output_dir: Directory to save the index

        Returns:
            Path to the saved index directory
        """
        output_dir = output_dir or self.config.index_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        with LogContext("Saving index"):
            # Save file entities
            entities_path = output_dir / "entities.json"
            entities_data = [
                {
                    "id": fe.id,
                    "name": fe.name,
                    "file_path": str(fe.file_path),
                    "language": fe.language.value,
                    "line_count": fe.line_count,
                    "namespace": fe.namespace,
                    "package": fe.package,
                    "imports": len(fe.imports),
                    "classes": len(fe.classes),
                    "functions": len(fe.functions),
                    "components": len(fe.components),
                }
                for fe in self._file_entities
            ]
            with open(entities_path, "w") as f:
                json.dump(entities_data, f, indent=2)

            # Save dependency graph
            if self._dependency_graph:
                graph_path = output_dir / "graph.json"
                with open(graph_path, "w") as f:
                    json.dump(self._dependency_graph.to_dict(), f, indent=2)

            # Save statistics
            if self._stats:
                stats_path = output_dir / "stats.json"
                with open(stats_path, "w") as f:
                    json.dump(self._stats.to_dict(), f, indent=2)

            logger.info(f"Index saved to {output_dir}")

        return output_dir

    def load_index(self, index_dir: Path) -> bool:
        """Load a previously saved index.

        Args:
            index_dir: Directory containing the saved index

        Returns:
            True if loaded successfully
        """
        try:
            with LogContext("Loading index"):
                # Load entities (minimal for now)
                entities_path = index_dir / "entities.json"
                if entities_path.exists():
                    with open(entities_path) as f:
                        entities_data = json.load(f)
                    logger.info(f"Loaded {len(entities_data)} file entities")

                # Load graph
                graph_path = index_dir / "graph.json"
                if graph_path.exists():
                    with open(graph_path) as f:
                        graph_data = json.load(f)
                    # Reconstruct graph (simplified)
                    self._dependency_graph = DependencyGraph()
                    logger.info(f"Loaded graph with {len(graph_data.get('nodes', []))} nodes")

                # Load stats
                stats_path = index_dir / "stats.json"
                if stats_path.exists():
                    with open(stats_path) as f:
                        stats_data = json.load(f)
                    # Reconstruct stats
                    self._stats = CodebaseStats(**stats_data)

                return True

        except Exception as e:
            logger.error(f"Failed to load index: {e}")
            return False

    @property
    def file_entities(self) -> list[FileEntity]:
        """Get the parsed file entities."""
        return self._file_entities

    @property
    def dependency_graph(self) -> DependencyGraph | None:
        """Get the dependency graph."""
        return self._dependency_graph

    @property
    def stats(self) -> CodebaseStats | None:
        """Get the codebase statistics."""
        return self._stats


def create_indexer(config: AppConfig | None = None) -> CodebaseIndexer:
    """Create an indexer instance.

    Args:
        config: Optional configuration

    Returns:
        Configured indexer instance
    """
    return CodebaseIndexer(config)
