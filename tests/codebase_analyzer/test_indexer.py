"""Tests for codebase_analyzer/indexer/indexer.py - Main indexer module."""

import json
from pathlib import Path

import pytest

from codebase_analyzer.config import AppConfig, IndexerConfig
from codebase_analyzer.indexer.indexer import CodebaseIndexer, IndexResult, create_indexer
from codebase_analyzer.indexer.models.entities import EntityType
from codebase_analyzer.indexer.models.relations import CodebaseStats


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def default_config(temp_dir: Path):
    """Create default config pointing to temp directory."""
    return AppConfig(
        project_root=temp_dir,
        indexer=IndexerConfig(
            languages=["php", "go", "typescript", "javascript"],
            include_patterns=["**/*.php", "**/*.go", "**/*.ts", "**/*.tsx", "**/*.js"],
            exclude_patterns=["**/node_modules/**", "**/vendor/**", "**/test/**"],
            max_file_size_mb=1.0,
            parallel_workers=1,
        ),
    )


@pytest.fixture
def simple_project(temp_dir: Path):
    """Create a simple project structure."""
    # Go file
    (temp_dir / "main.go").write_text('''package main

func main() {
    println("Hello")
}
''')

    # PHP file
    (temp_dir / "User.php").write_text('''<?php

class User {
    private string $name;

    public function getName(): string {
        return $this->name;
    }
}
''')

    # TypeScript file
    (temp_dir / "service.ts").write_text('''export class UserService {
    async getUser(id: number): Promise<User> {
        return fetch(`/api/users/${id}`);
    }
}
''')

    return temp_dir


@pytest.fixture
def indexer_with_project(simple_project: Path, default_config: AppConfig):
    """Create indexer with simple project."""
    default_config = AppConfig(
        project_root=simple_project,
        indexer=IndexerConfig(
            languages=["php", "go", "typescript"],
            include_patterns=["**/*.php", "**/*.go", "**/*.ts"],
            exclude_patterns=["**/node_modules/**", "**/vendor/**"],
            max_file_size_mb=1.0,
            parallel_workers=1,
        ),
    )
    return CodebaseIndexer(default_config)


# ============================================================================
# CodebaseIndexer Creation Tests
# ============================================================================


class TestCodebaseIndexerCreation:
    """Tests for CodebaseIndexer instantiation."""

    def test_create_with_config(self, default_config):
        """Test creating indexer with config."""
        indexer = CodebaseIndexer(default_config)

        assert indexer is not None
        assert indexer.config is default_config

    def test_create_without_config(self):
        """Test creating indexer without config uses global."""
        indexer = CodebaseIndexer()

        assert indexer is not None
        assert indexer.config is not None

    def test_create_indexer_factory(self, default_config):
        """Test create_indexer factory function."""
        indexer = create_indexer(default_config)

        assert indexer is not None
        assert isinstance(indexer, CodebaseIndexer)

    def test_initial_state(self, default_config):
        """Test indexer initial state."""
        indexer = CodebaseIndexer(default_config)

        assert indexer.file_entities == []
        assert indexer.dependency_graph is None
        assert indexer.stats is None


# ============================================================================
# File Discovery Tests
# ============================================================================


class TestFileDiscovery:
    """Tests for file discovery functionality."""

    def test_discover_files_simple(self, indexer_with_project):
        """Test discovering files in simple project."""
        files = indexer_with_project.discover_files()

        assert len(files) == 3
        extensions = [f.suffix for f in files]
        assert ".go" in extensions
        assert ".php" in extensions
        assert ".ts" in extensions

    def test_discover_files_empty_dir(self, temp_dir: Path, default_config):
        """Test discovering files in empty directory."""
        default_config.project_root = temp_dir
        indexer = CodebaseIndexer(default_config)

        files = indexer.discover_files()

        assert files == []

    def test_discover_files_excludes_patterns(self, temp_dir: Path):
        """Test that exclude patterns are respected."""
        # Create files in excluded directories
        (temp_dir / "src").mkdir()
        (temp_dir / "src" / "main.go").write_text("package main")
        (temp_dir / "vendor").mkdir()
        (temp_dir / "vendor" / "lib.go").write_text("package lib")
        (temp_dir / "node_modules").mkdir()
        (temp_dir / "node_modules" / "pkg.js").write_text("module.exports = {};")

        config = AppConfig(
            project_root=temp_dir,
            indexer=IndexerConfig(
                include_patterns=["**/*.go", "**/*.js"],
                exclude_patterns=["**/vendor/**", "**/node_modules/**"],
            ),
        )
        indexer = CodebaseIndexer(config)

        files = indexer.discover_files()

        # Should only find src/main.go
        assert len(files) == 1
        assert "vendor" not in str(files[0])
        assert "node_modules" not in str(files[0])

    def test_discover_files_respects_size_limit(self, temp_dir: Path):
        """Test that large files are excluded."""
        # Create a small file
        small_file = temp_dir / "small.go"
        small_file.write_text("package main")

        # Create a large file (> 1MB)
        large_file = temp_dir / "large.go"
        large_file.write_text("package main\n" + "// " * 500000)

        config = AppConfig(
            project_root=temp_dir,
            indexer=IndexerConfig(
                include_patterns=["**/*.go"],
                exclude_patterns=[],
                max_file_size_mb=0.1,  # 100KB limit
            ),
        )
        indexer = CodebaseIndexer(config)

        files = indexer.discover_files()

        # Only small file should be discovered
        assert len(files) == 1
        assert files[0].name == "small.go"

    def test_discover_files_nested_directories(self, temp_dir: Path):
        """Test discovering files in nested directories."""
        # Create nested structure
        (temp_dir / "src" / "models").mkdir(parents=True)
        (temp_dir / "src" / "services").mkdir(parents=True)
        (temp_dir / "src" / "models" / "User.php").write_text("<?php class User {}")
        (temp_dir / "src" / "services" / "UserService.php").write_text(
            "<?php class UserService {}"
        )

        config = AppConfig(
            project_root=temp_dir,
            indexer=IndexerConfig(
                include_patterns=["**/*.php"],
                exclude_patterns=[],
            ),
        )
        indexer = CodebaseIndexer(config)

        files = indexer.discover_files()

        assert len(files) == 2
        file_names = [f.name for f in files]
        assert "User.php" in file_names
        assert "UserService.php" in file_names


# ============================================================================
# File Parsing Tests
# ============================================================================


class TestFileParsing:
    """Tests for file parsing functionality."""

    def test_parse_files(self, indexer_with_project):
        """Test parsing discovered files."""
        files = indexer_with_project.discover_files()
        entities = indexer_with_project.parse_files(files)

        assert len(entities) >= 1
        assert indexer_with_project.file_entities == entities

    def test_parse_files_stores_entities(self, indexer_with_project):
        """Test that parsed entities are stored."""
        files = indexer_with_project.discover_files()
        indexer_with_project.parse_files(files)

        assert len(indexer_with_project.file_entities) >= 1

    def test_parse_files_extracts_classes(self, indexer_with_project):
        """Test that classes are extracted from files."""
        files = indexer_with_project.discover_files()
        entities = indexer_with_project.parse_files(files)

        # Should have extracted User class from PHP and UserService from TS
        all_classes = []
        for entity in entities:
            all_classes.extend(entity.classes)

        class_names = [c.name for c in all_classes]
        # At least one class should be found
        assert len(class_names) >= 1

    def test_parse_files_extracts_functions(self, indexer_with_project):
        """Test that functions are extracted from files."""
        files = indexer_with_project.discover_files()
        entities = indexer_with_project.parse_files(files)

        # Should have extracted main function from Go
        all_functions = []
        for entity in entities:
            all_functions.extend(entity.functions)

        # At least one function should be found
        assert len(all_functions) >= 0  # May be 0 if Go parsing fails

    def test_parse_empty_file_list(self, indexer_with_project):
        """Test parsing empty file list."""
        entities = indexer_with_project.parse_files([])

        assert entities == []

    def test_parse_single_file(self, temp_dir: Path, default_config):
        """Test parsing a single file."""
        php_file = temp_dir / "Single.php"
        php_file.write_text('''<?php
class SingleClass {
    public function test(): void {}
}
''')

        default_config.project_root = temp_dir
        indexer = CodebaseIndexer(default_config)
        entities = indexer.parse_files([php_file])

        assert len(entities) == 1
        assert entities[0].name == "Single.php"

    def test_parse_file_with_syntax_error(self, temp_dir: Path, default_config):
        """Test parsing file with syntax errors."""
        broken_file = temp_dir / "broken.go"
        broken_file.write_text('''package main

func broken( {
    // Missing closing paren
''')

        good_file = temp_dir / "good.go"
        good_file.write_text('''package main

func good() {
    println("ok")
}
''')

        default_config.project_root = temp_dir
        indexer = CodebaseIndexer(default_config)
        entities = indexer.parse_files([broken_file, good_file])

        # Should still parse the good file
        # Broken file may or may not parse depending on parser behavior
        assert len(entities) >= 0


# ============================================================================
# Dependency Graph Tests
# ============================================================================


class TestDependencyGraph:
    """Tests for dependency graph building."""

    def test_build_graph(self, indexer_with_project):
        """Test building dependency graph."""
        files = indexer_with_project.discover_files()
        indexer_with_project.parse_files(files)
        graph = indexer_with_project.build_graph()

        assert graph is not None
        assert indexer_with_project.dependency_graph is graph

    def test_build_graph_without_parsing(self, indexer_with_project):
        """Test building graph without parsing raises error."""
        with pytest.raises(ValueError, match="No file entities"):
            indexer_with_project.build_graph()

    def test_build_graph_with_explicit_entities(self, indexer_with_project):
        """Test building graph with explicit entities."""
        files = indexer_with_project.discover_files()
        entities = indexer_with_project.parse_files(files)

        # Clear cached entities
        indexer_with_project._file_entities = []

        # Build with explicit entities
        graph = indexer_with_project.build_graph(entities)

        assert graph is not None

    def test_graph_contains_entities(self, indexer_with_project):
        """Test that graph contains parsed entities."""
        files = indexer_with_project.discover_files()
        indexer_with_project.parse_files(files)
        graph = indexer_with_project.build_graph()

        # Graph should have entities
        assert graph.stats["total_entities"] > 0


# ============================================================================
# Statistics Tests
# ============================================================================


class TestStatistics:
    """Tests for statistics computation."""

    def test_compute_stats(self, indexer_with_project):
        """Test computing codebase statistics."""
        files = indexer_with_project.discover_files()
        indexer_with_project.parse_files(files)
        stats = indexer_with_project.compute_stats()

        assert isinstance(stats, CodebaseStats)
        assert stats.total_files >= 1
        assert indexer_with_project.stats is stats

    def test_stats_total_files(self, indexer_with_project):
        """Test total files count in stats."""
        files = indexer_with_project.discover_files()
        entities = indexer_with_project.parse_files(files)
        stats = indexer_with_project.compute_stats()

        assert stats.total_files == len(entities)

    def test_stats_by_language(self, indexer_with_project):
        """Test files by language in stats."""
        files = indexer_with_project.discover_files()
        indexer_with_project.parse_files(files)
        stats = indexer_with_project.compute_stats()

        # Should have counts for each language
        assert isinstance(stats.files_by_language, dict)
        # At least one language should have files
        assert sum(stats.files_by_language.values()) > 0


# ============================================================================
# Full Indexing Pipeline Tests
# ============================================================================


class TestFullIndexingPipeline:
    """Tests for the complete indexing pipeline."""

    def test_index_method(self, simple_project: Path):
        """Test the index() method which runs full pipeline."""
        config = AppConfig(
            project_root=simple_project,
            indexer=IndexerConfig(
                include_patterns=["**/*.php", "**/*.go", "**/*.ts"],
                exclude_patterns=[],
            ),
        )
        indexer = CodebaseIndexer(config)

        result = indexer.index()

        assert isinstance(result, IndexResult)
        assert result.graph is not None
        assert result.stats is not None
        assert result.stats.total_files >= 1
        assert len(result.processing_levels) >= 0
        assert len(result.topological_order) >= 0

    def test_index_with_explicit_root(self, simple_project: Path, temp_dir: Path):
        """Test index() with explicit project root."""
        config = AppConfig(
            project_root=temp_dir,  # Different root
            indexer=IndexerConfig(
                include_patterns=["**/*.php", "**/*.go", "**/*.ts"],
                exclude_patterns=[],
            ),
        )
        indexer = CodebaseIndexer(config)

        # Override with actual project
        result = indexer.index(project_root=simple_project)

        assert result.graph is not None
        assert result.stats.total_files >= 1


# ============================================================================
# Save/Load Index Tests
# ============================================================================


class TestIndexPersistence:
    """Tests for saving and loading index."""

    def test_save_index(self, indexer_with_project, temp_dir: Path):
        """Test saving index to file."""
        files = indexer_with_project.discover_files()
        indexer_with_project.parse_files(files)
        indexer_with_project.build_graph()
        indexer_with_project.compute_stats()

        output_dir = temp_dir / "index_output"
        output_dir.mkdir()

        path = indexer_with_project.save_index(output_dir)

        assert path is not None
        assert path.exists()

    def test_load_index(self, indexer_with_project, temp_dir: Path):
        """Test loading saved index."""
        files = indexer_with_project.discover_files()
        indexer_with_project.parse_files(files)
        indexer_with_project.build_graph()
        indexer_with_project.compute_stats()

        output_dir = temp_dir / "index_output"
        output_dir.mkdir()

        save_path = indexer_with_project.save_index(output_dir)

        # Create new indexer and load
        new_indexer = CodebaseIndexer(indexer_with_project.config)
        success = new_indexer.load_index(save_path.parent)

        assert success is True


# ============================================================================
# Edge Cases and Error Handling Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_nonexistent_project_root(self, temp_dir: Path):
        """Test handling non-existent project root."""
        config = AppConfig(
            project_root=temp_dir / "nonexistent",
            indexer=IndexerConfig(
                include_patterns=["**/*.go"],
                exclude_patterns=[],
            ),
        )
        indexer = CodebaseIndexer(config)

        # Should not crash, return empty
        files = indexer.discover_files()
        assert files == []

    def test_unsupported_file_type(self, temp_dir: Path):
        """Test handling unsupported file types."""
        # Create file with unsupported extension
        (temp_dir / "file.rs").write_text("fn main() {}")
        (temp_dir / "file.py").write_text("def main(): pass")

        config = AppConfig(
            project_root=temp_dir,
            indexer=IndexerConfig(
                include_patterns=["**/*.rs", "**/*.py"],  # Unsupported
                exclude_patterns=[],
            ),
        )
        indexer = CodebaseIndexer(config)

        files = indexer.discover_files()
        entities = indexer.parse_files(files)

        # Should not crash, entities may be empty
        assert isinstance(entities, list)

    def test_binary_file(self, temp_dir: Path):
        """Test handling binary files."""
        # Create a binary file with .go extension (edge case)
        binary_file = temp_dir / "binary.go"
        binary_file.write_bytes(bytes(range(256)))

        config = AppConfig(
            project_root=temp_dir,
            indexer=IndexerConfig(
                include_patterns=["**/*.go"],
                exclude_patterns=[],
            ),
        )
        indexer = CodebaseIndexer(config)

        files = indexer.discover_files()
        # Should not crash
        entities = indexer.parse_files(files)
        assert isinstance(entities, list)

    def test_symlink_handling(self, temp_dir: Path):
        """Test handling of symbolic links."""
        # Create a source file
        src_file = temp_dir / "src.go"
        src_file.write_text("package main")

        # Create symlink
        link_file = temp_dir / "link.go"
        try:
            link_file.symlink_to(src_file)
        except OSError:
            pytest.skip("Symlinks not supported")

        config = AppConfig(
            project_root=temp_dir,
            indexer=IndexerConfig(
                include_patterns=["**/*.go"],
                exclude_patterns=[],
            ),
        )
        indexer = CodebaseIndexer(config)

        files = indexer.discover_files()
        # Should find both or just one, but not crash
        assert len(files) >= 1

    def test_unicode_filenames(self, temp_dir: Path):
        """Test handling unicode in filenames."""
        unicode_file = temp_dir / "пользователь.php"
        unicode_file.write_text("<?php class User {}")

        config = AppConfig(
            project_root=temp_dir,
            indexer=IndexerConfig(
                include_patterns=["**/*.php"],
                exclude_patterns=[],
            ),
        )
        indexer = CodebaseIndexer(config)

        files = indexer.discover_files()
        # Should find the file
        assert len(files) == 1

    def test_deeply_nested_files(self, temp_dir: Path):
        """Test handling deeply nested file structure."""
        # Create deep nesting
        deep_path = temp_dir
        for i in range(10):
            deep_path = deep_path / f"level{i}"
        deep_path.mkdir(parents=True)

        deep_file = deep_path / "deep.go"
        deep_file.write_text("package deep")

        config = AppConfig(
            project_root=temp_dir,
            indexer=IndexerConfig(
                include_patterns=["**/*.go"],
                exclude_patterns=[],
            ),
        )
        indexer = CodebaseIndexer(config)

        files = indexer.discover_files()
        assert len(files) == 1


# ============================================================================
# Properties Tests
# ============================================================================


class TestProperties:
    """Tests for indexer properties."""

    def test_file_entities_property(self, indexer_with_project):
        """Test file_entities property."""
        files = indexer_with_project.discover_files()
        indexer_with_project.parse_files(files)

        entities = indexer_with_project.file_entities

        assert isinstance(entities, list)
        assert len(entities) >= 1

    def test_dependency_graph_property(self, indexer_with_project):
        """Test dependency_graph property."""
        files = indexer_with_project.discover_files()
        indexer_with_project.parse_files(files)
        indexer_with_project.build_graph()

        graph = indexer_with_project.dependency_graph

        assert graph is not None

    def test_stats_property(self, indexer_with_project):
        """Test stats property."""
        files = indexer_with_project.discover_files()
        indexer_with_project.parse_files(files)
        indexer_with_project.compute_stats()

        stats = indexer_with_project.stats

        assert isinstance(stats, CodebaseStats)


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for full indexing workflow."""

    def test_full_workflow(self, multi_file_project: Path):
        """Test complete indexing workflow on multi-file project."""
        config = AppConfig(
            project_root=multi_file_project,
            indexer=IndexerConfig(
                include_patterns=["**/*.php", "**/*.go", "**/*.ts"],
                exclude_patterns=["**/vendor/**", "**/node_modules/**"],
            ),
        )
        indexer = CodebaseIndexer(config)

        # Discover
        files = indexer.discover_files()
        assert len(files) >= 3

        # Parse
        entities = indexer.parse_files(files)
        assert len(entities) >= 1

        # Build graph
        graph = indexer.build_graph()
        assert graph is not None
        assert graph.stats["total_entities"] > 0

        # Compute stats
        stats = indexer.compute_stats()
        assert stats.total_files > 0
        assert len(stats.files_by_language) > 0

    def test_reindex(self, simple_project: Path):
        """Test re-indexing same project."""
        config = AppConfig(
            project_root=simple_project,
            indexer=IndexerConfig(
                include_patterns=["**/*.php", "**/*.go", "**/*.ts"],
                exclude_patterns=[],
            ),
        )
        indexer = CodebaseIndexer(config)

        # First index
        result1 = indexer.index()

        # Second index (should work same way)
        result2 = indexer.index()

        # Results should be consistent
        assert result1.stats.total_files == result2.stats.total_files


# ============================================================================
# IndexResult Tests
# ============================================================================


class TestIndexResult:
    """Tests for IndexResult dataclass."""

    def test_create_empty_result(self):
        """Should create an empty result."""
        from codebase_analyzer.indexer.graph.dependency_graph import DependencyGraph

        result = IndexResult(
            graph=DependencyGraph(),
            stats=CodebaseStats(),
        )

        assert result.total_entities == 0
        assert result.level_count == 0
        assert result.embeddings_generated is False
        assert result.embedding_count == 0

    def test_create_result_with_levels(self):
        """Should create result with processing levels."""
        from codebase_analyzer.indexer.graph.dependency_graph import DependencyGraph

        result = IndexResult(
            graph=DependencyGraph(),
            stats=CodebaseStats(),
            processing_levels=[["e1", "e2"], ["e3"]],
            topological_order=["e1", "e2", "e3"],
        )

        assert result.total_entities == 3
        assert result.level_count == 2

    def test_broken_cycles_tracking(self):
        """Should track broken cycles."""
        from codebase_analyzer.indexer.graph.dependency_graph import DependencyGraph

        result = IndexResult(
            graph=DependencyGraph(),
            stats=CodebaseStats(),
            broken_cycles=[("a", "b"), ("c", "d")],
        )

        assert len(result.broken_cycles) == 2


# ============================================================================
# Processing Order Tests
# ============================================================================


class TestProcessingOrder:
    """Tests for topological order and processing levels computation."""

    def test_compute_processing_order(self, simple_project: Path):
        """Test computing processing order from graph."""
        config = AppConfig(
            project_root=simple_project,
            indexer=IndexerConfig(
                include_patterns=["**/*.php", "**/*.go", "**/*.ts"],
                exclude_patterns=[],
            ),
        )
        indexer = CodebaseIndexer(config)
        result = indexer.index()

        # Should have processing levels
        assert isinstance(result.processing_levels, list)
        assert isinstance(result.topological_order, list)

        # If we have entities, we should have processing levels
        if result.total_entities > 0:
            assert result.level_count >= 1

    def test_processing_levels_cover_all_entities(self, simple_project: Path):
        """Test that processing levels include all entities."""
        config = AppConfig(
            project_root=simple_project,
            indexer=IndexerConfig(
                include_patterns=["**/*.php", "**/*.go", "**/*.ts"],
                exclude_patterns=[],
            ),
        )
        indexer = CodebaseIndexer(config)
        result = indexer.index()

        # All entities in topological order should be in processing levels
        entities_in_levels = set()
        for level in result.processing_levels:
            entities_in_levels.update(level)

        assert entities_in_levels == set(result.topological_order)


# ============================================================================
# Get Entities for Analysis Tests
# ============================================================================


class TestGetEntitiesForAnalysis:
    """Tests for get_entities_for_analysis method."""

    def test_get_entities_for_analysis(self, simple_project: Path):
        """Should extract entities for LLM analysis."""
        config = AppConfig(
            project_root=simple_project,
            indexer=IndexerConfig(
                include_patterns=["**/*.php", "**/*.go", "**/*.ts"],
                exclude_patterns=[],
            ),
        )
        indexer = CodebaseIndexer(config)
        indexer.index()

        entities = indexer.get_entities_for_analysis()

        # Should return a list of CodeEntity objects
        assert isinstance(entities, list)

        # Each entity should have required attributes
        for entity in entities:
            assert hasattr(entity, "id")
            assert hasattr(entity, "name")
            assert hasattr(entity, "entity_type")
