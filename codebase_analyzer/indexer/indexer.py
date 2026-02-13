"""Main indexer module for orchestrating code parsing and indexing."""

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from ..config import AppConfig, get_config
from ..utils.logging import LogContext, get_logger
from ..utils.progress import create_progress, get_metrics, reset_metrics
from .graph.dependency_graph import DependencyGraph, build_dependency_graph
from .models.entities import (
    CodeEntity,
    EntityType,
    FileEntity,
    Language,
    SourceLocation,
)
from .models.relations import CodebaseStats, Relation, RelationType
from .parsers.base import get_parser_for_file

logger = get_logger("indexer")


@dataclass
class IndexResult:
    """Result of indexing operation."""

    graph: DependencyGraph
    stats: CodebaseStats
    processing_levels: list[list[str]] = field(default_factory=list)
    topological_order: list[str] = field(default_factory=list)
    broken_cycles: list[tuple[str, str]] = field(default_factory=list)
    embeddings_generated: bool = False
    embedding_count: int = 0

    @property
    def total_entities(self) -> int:
        return len(self.topological_order)

    @property
    def level_count(self) -> int:
        return len(self.processing_levels)


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

    def index(
        self,
        project_root: Path | None = None,
        generate_embeddings: bool = False,
    ) -> IndexResult:
        """Run the full indexing pipeline.

        Args:
            project_root: Optional project root to override config
            generate_embeddings: Whether to generate code embeddings

        Returns:
            IndexResult with graph, stats, and processing levels
        """
        if project_root:
            self.config.project_root = project_root

        reset_metrics()

        logger.info(f"Starting indexing of {self.config.project_root}")

        # Discover files
        files = self.discover_files()

        if not files:
            logger.warning("No source files found to index")
            return IndexResult(
                graph=DependencyGraph(),
                stats=CodebaseStats(),
            )

        # Parse files
        file_entities = self.parse_files(files)

        if not file_entities:
            logger.warning("No files were successfully parsed")
            return IndexResult(
                graph=DependencyGraph(),
                stats=CodebaseStats(),
            )

        # Build graph
        graph = self.build_graph(file_entities)

        # Compute topological order and processing levels
        topological_order, processing_levels, broken_cycles = self._compute_processing_order(graph)

        # Compute stats
        stats = self.compute_stats()

        # Generate embeddings if requested
        embedding_count = 0
        if generate_embeddings:
            embedding_count = self._generate_embeddings(file_entities)

        # Print summary
        get_metrics().print_summary()

        return IndexResult(
            graph=graph,
            stats=stats,
            processing_levels=processing_levels,
            topological_order=topological_order,
            broken_cycles=broken_cycles,
            embeddings_generated=generate_embeddings,
            embedding_count=embedding_count,
        )

    def _compute_processing_order(
        self,
        graph: DependencyGraph,
    ) -> tuple[list[str], list[list[str]], list[tuple[str, str]]]:
        """Compute topological order and processing levels.

        Returns:
            Tuple of (topological_order, processing_levels, broken_cycles)
        """
        with LogContext("Computing processing order"):
            # Break cycles if needed
            broken_edges = graph.break_cycles()
            broken_cycles = [(e[0], e[1]) for e in broken_edges]

            if broken_cycles:
                logger.info(f"Broke {len(broken_cycles)} cycles in dependency graph")

            # Get topological order
            topological_order = graph.get_topological_order(break_cycles_if_needed=False)

            # Get processing levels for parallel execution
            processing_levels = graph.get_processing_levels(break_cycles_if_needed=False)

            logger.info(
                f"Computed {len(processing_levels)} processing levels "
                f"for {len(topological_order)} entities"
            )

        return topological_order, processing_levels, broken_cycles

    def _generate_embeddings(self, file_entities: list[FileEntity]) -> int:
        """Generate embeddings for all code entities.

        Returns:
            Number of embeddings generated
        """
        try:
            from .embeddings import CodeEmbedder, EmbeddingStore, StoreConfig

            with LogContext("Generating embeddings"):
                # Collect all entities
                all_entities: list[CodeEntity] = []
                for fe in file_entities:
                    all_entities.extend(fe.all_entities)

                if not all_entities:
                    return 0

                # Initialize embedder and store
                embedder = CodeEmbedder()
                store_config = StoreConfig(
                    mode="local",
                    local_path=self.config.index_dir / "embeddings",
                )
                store = EmbeddingStore(store_config)

                # Generate embeddings in batches
                embeddings = embedder.embed_entities(
                    all_entities,
                    show_progress=True,
                )

                # Store embeddings
                store.add_many(embeddings)

                logger.info(f"Generated {len(embeddings)} embeddings")
                return len(embeddings)

        except ImportError as e:
            logger.warning(f"Embeddings not available: {e}")
            return 0
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            return 0

    def save_index(
        self,
        output_dir: Path | None = None,
        index_result: IndexResult | None = None,
    ) -> Path:
        """Save the index to disk.

        Args:
            output_dir: Directory to save the index
            index_result: Optional index result with processing levels

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

            # Save processing levels and topological order
            if index_result:
                order_path = output_dir / "processing_order.json"
                order_data = {
                    "topological_order": index_result.topological_order,
                    "processing_levels": index_result.processing_levels,
                    "broken_cycles": index_result.broken_cycles,
                }
                with open(order_path, "w") as f:
                    json.dump(order_data, f, indent=2)

            logger.info(f"Index saved to {output_dir}")

        return output_dir

    def get_entities_for_analysis(self) -> list[CodeEntity]:
        """Get all code entities for LLM analysis.

        Returns entities in a flat list suitable for summarization.
        """
        entities: list[CodeEntity] = []

        for fe in self._file_entities:
            # Add classes (but not the file entity itself)
            for cls in fe.classes:
                entities.append(cls)
                # Add methods of the class
                for method in cls.methods:
                    entities.append(method)

            # Add standalone functions
            for func in fe.functions:
                entities.append(func)

            # Add components (React)
            for comp in fe.components:
                entities.append(comp)

        return entities

    def load_index(self, index_dir: Path) -> bool:
        """Load a previously saved index.

        Reconstructs the full dependency graph from graph.json and re-reads
        source files from disk to populate entity source_code (needed by the
        analysis pipeline / LLM summarizer).

        Args:
            index_dir: Directory containing the saved index

        Returns:
            True if loaded successfully
        """
        try:
            with LogContext("Loading index"):
                # Load entities metadata
                entities_path = index_dir / "entities.json"
                if entities_path.exists():
                    with open(entities_path) as f:
                        entities_data = json.load(f)
                    logger.info(f"Loaded {len(entities_data)} file entities")

                # Load and reconstruct graph
                graph_path = index_dir / "graph.json"
                if graph_path.exists():
                    with open(graph_path) as f:
                        graph_data = json.load(f)

                    graph = DependencyGraph()

                    # Cache: file_path -> source content (read once per file)
                    _file_source_cache: dict[str, str] = {}

                    # 1) Reconstruct entities from graph nodes
                    for node in graph_data.get("nodes", []):
                        entity_id = node["id"]
                        entity_type_str = node.get("entity_type", "file")
                        name = node.get("name", "")
                        lang_str = node.get("language", "typescript")
                        file_str = node.get("file", "")

                        # Map strings to enums
                        try:
                            entity_type = EntityType(entity_type_str)
                        except ValueError:
                            entity_type = EntityType.FILE
                        try:
                            language = Language(lang_str)
                        except ValueError:
                            language = Language.TYPESCRIPT

                        file_path = Path(file_str) if file_str else Path("unknown")

                        # Read source code from disk (cached per file)
                        source_code = ""
                        if file_str and file_str not in _file_source_cache:
                            try:
                                _file_source_cache[file_str] = Path(file_str).read_text(
                                    encoding="utf-8", errors="replace"
                                )
                            except OSError:
                                _file_source_cache[file_str] = ""
                        if file_str:
                            source_code = _file_source_cache.get(file_str, "")

                        entity = CodeEntity(
                            id=entity_id,
                            name=name,
                            entity_type=entity_type,
                            language=language,
                            location=SourceLocation(
                                file_path=file_path,
                                start_line=1,
                                end_line=max(1, source_code.count("\n") + 1),
                            ),
                            source_code=source_code,
                        )
                        graph.add_entity(entity)

                    # 2) Reconstruct edges
                    for edge in graph_data.get("edges", []):
                        source_id = edge["source"]
                        target_id = edge["target"]
                        rel_type_str = edge.get("relation_type", "depends_on")
                        try:
                            rel_type = RelationType(rel_type_str)
                        except ValueError:
                            rel_type = RelationType.IMPORTS
                        relation = Relation.create(source_id, target_id, rel_type)
                        graph.add_relation(relation)

                    self._dependency_graph = graph
                    logger.info(
                        f"Loaded graph with {len(graph_data.get('nodes', []))} nodes"
                    )

                # Load stats
                stats_path = index_dir / "stats.json"
                if stats_path.exists():
                    with open(stats_path) as f:
                        stats_data = json.load(f)
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
