"""Tests for CLI commands."""

import json
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

import pytest
from typer.testing import CliRunner

from codebase_analyzer.main import app
from codebase_analyzer.analyzer.models import (
    AnalysisResult,
    ArchitectureSummary,
    EntitySummary,
    ModuleSummary,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_index_dir(tmp_path):
    """Create a temporary index directory with required files."""
    index_dir = tmp_path / "index"
    index_dir.mkdir()

    # Create minimal index files
    entities_data = [
        {
            "id": "test::entity",
            "name": "test_entity",
            "file_path": "/test/file.go",
            "language": "go",
            "line_count": 100,
        }
    ]
    (index_dir / "entities.json").write_text(json.dumps(entities_data))

    stats_data = {
        "total_files": 1,
        "total_lines": 100,
        "total_classes": 1,
        "total_functions": 5,
        "total_methods": 10,
        "files_by_language": {"go": 1},
        "lines_by_language": {"go": 100},
    }
    (index_dir / "stats.json").write_text(json.dumps(stats_data))

    graph_data = {
        "nodes": [{"id": "test::entity", "entity_type": "class"}],
        "edges": [],
    }
    (index_dir / "graph.json").write_text(json.dumps(graph_data))

    return index_dir


@pytest.fixture
def temp_analysis_file(tmp_path):
    """Create a temporary analysis file."""
    analysis_dir = tmp_path / "analysis"
    analysis_dir.mkdir()

    result = AnalysisResult(
        entity_summaries={
            "test::entity": EntitySummary(
                entity_id="test::entity",
                summary="A test entity",
                purpose="Testing",
                domain="test",
            ),
        },
        module_summaries={
            "src/test": ModuleSummary(
                path="src/test",
                name="test",
                summary="Test module",
                entities=["test::entity"],
                entity_count=1,
                total_lines=100,
            ),
        },
        architecture=ArchitectureSummary(
            overview="A test application",
            modules=["src/test"],
            patterns_detected=["MVC"],
            tech_stack=["Go"],
        ),
        total_entities=1,
        total_modules=1,
    )

    analysis_file = analysis_dir / "analysis.json"
    result.save(analysis_file)

    return analysis_file


@pytest.fixture
def temp_output_dir(tmp_path):
    """Create a temporary output directory."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return output_dir


# =============================================================================
# Version and Help Tests
# =============================================================================


class TestVersionAndHelp:
    """Tests for version and help commands."""

    def test_version(self, runner):
        """Test --version flag."""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "version" in result.stdout.lower()

    def test_help(self, runner):
        """Test --help flag."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "codebase-analyzer" in result.stdout.lower() or "analyze" in result.stdout.lower()

    def test_analyze_help(self, runner):
        """Test analyze --help."""
        result = runner.invoke(app, ["analyze", "--help"])
        assert result.exit_code == 0
        assert "index" in result.stdout.lower()

    def test_generate_help(self, runner):
        """Test generate --help."""
        result = runner.invoke(app, ["generate", "--help"])
        assert result.exit_code == 0
        assert "analysis" in result.stdout.lower()


# =============================================================================
# Stats Command Tests
# =============================================================================


class TestStatsCommand:
    """Tests for the stats command."""

    def test_stats_command(self, runner, temp_index_dir):
        """Test stats command with valid index."""
        result = runner.invoke(app, ["stats", str(temp_index_dir)])
        assert result.exit_code == 0
        assert "Total Files" in result.stdout

    def test_stats_no_index(self, runner, tmp_path):
        """Test stats command with missing index."""
        missing_dir = tmp_path / "missing"
        missing_dir.mkdir()
        result = runner.invoke(app, ["stats", str(missing_dir)])
        assert result.exit_code == 1


# =============================================================================
# Index Command Tests
# =============================================================================


class TestIndexCommand:
    """Tests for the index command."""

    def test_index_help(self, runner):
        """Test index --help."""
        result = runner.invoke(app, ["index", "--help"])
        assert result.exit_code == 0
        assert "index" in result.stdout.lower()

    @patch("codebase_analyzer.main.create_indexer")
    def test_index_command_creates_index(self, mock_create_indexer, runner, tmp_path):
        """Test index command creates index files."""
        # Setup mocks
        mock_indexer = Mock()
        mock_indexer.index.return_value = (Mock(), Mock(
            total_files=10,
            total_lines=1000,
            total_classes=5,
            total_interfaces=2,
            total_traits=0,
            total_functions=20,
            total_methods=50,
            total_components=0,
            total_imports=100,
            total_relations=30,
            files_by_language={"go": 10},
            lines_by_language={"go": 1000},
        ))
        mock_indexer.save_index.return_value = tmp_path / "index"
        mock_create_indexer.return_value = mock_indexer

        # Create a dummy source directory
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "main.go").write_text("package main")

        result = runner.invoke(app, ["index", str(source_dir)])

        # Should complete (though actual indexing is mocked)
        mock_create_indexer.assert_called_once()


# =============================================================================
# Generate Command Tests
# =============================================================================


class TestGenerateCommand:
    """Tests for the generate command."""

    def test_generate_from_file(self, runner, temp_analysis_file, temp_output_dir):
        """Test generate command with analysis file."""
        result = runner.invoke(
            app,
            ["generate", str(temp_analysis_file), "-o", str(temp_output_dir)],
        )
        assert result.exit_code == 0
        assert "Generated" in result.stdout
        assert (temp_output_dir / "README.md").exists()

    def test_generate_from_directory(self, runner, temp_analysis_file, temp_output_dir):
        """Test generate command with directory containing analysis.json."""
        analysis_dir = temp_analysis_file.parent
        result = runner.invoke(
            app,
            ["generate", str(analysis_dir), "-o", str(temp_output_dir)],
        )
        assert result.exit_code == 0
        assert (temp_output_dir / "README.md").exists()

    def test_generate_with_title(self, runner, temp_analysis_file, temp_output_dir):
        """Test generate command with custom title."""
        result = runner.invoke(
            app,
            ["generate", str(temp_analysis_file), "-o", str(temp_output_dir), "-t", "My Project"],
        )
        assert result.exit_code == 0

        readme_content = (temp_output_dir / "README.md").read_text()
        assert "My Project" in readme_content

    def test_generate_no_modules(self, runner, temp_analysis_file, temp_output_dir):
        """Test generate command with --no-modules."""
        result = runner.invoke(
            app,
            ["generate", str(temp_analysis_file), "-o", str(temp_output_dir), "--no-modules"],
        )
        assert result.exit_code == 0
        # Should not create modules directory
        assert not (temp_output_dir / "modules").exists()

    def test_generate_no_api(self, runner, temp_analysis_file, temp_output_dir):
        """Test generate command with --no-api."""
        result = runner.invoke(
            app,
            ["generate", str(temp_analysis_file), "-o", str(temp_output_dir), "--no-api"],
        )
        assert result.exit_code == 0
        # Should not create API.md
        assert not (temp_output_dir / "API.md").exists()

    def test_generate_missing_analysis(self, runner, tmp_path, temp_output_dir):
        """Test generate command with missing analysis file."""
        missing_file = tmp_path / "missing.json"
        result = runner.invoke(
            app,
            ["generate", str(missing_file), "-o", str(temp_output_dir)],
        )
        # Typer should fail because file doesn't exist
        assert result.exit_code != 0


# =============================================================================
# Config Command Tests
# =============================================================================


class TestConfigCommand:
    """Tests for the config command."""

    def test_config_show(self, runner):
        """Test config --show."""
        result = runner.invoke(app, ["config", "--show"])
        assert result.exit_code == 0

    def test_config_output(self, runner, tmp_path):
        """Test config --output."""
        config_file = tmp_path / "config.yaml"
        result = runner.invoke(app, ["config", "-o", str(config_file)])
        assert result.exit_code == 0
        assert config_file.exists()


# =============================================================================
# Analyze Command Tests
# =============================================================================


class TestAnalyzeCommand:
    """Tests for the analyze command."""

    def test_analyze_help(self, runner):
        """Test analyze --help shows all options."""
        result = runner.invoke(app, ["analyze", "--help"])
        assert result.exit_code == 0
        assert "--incremental" in result.stdout
        assert "--model" in result.stdout
        assert "--api-base" in result.stdout

    @patch("codebase_analyzer.main.create_indexer")
    @patch("codebase_analyzer.main.AnalysisPipeline")
    @patch("codebase_analyzer.main.asyncio.run")
    def test_analyze_loads_index(
        self,
        mock_asyncio_run,
        mock_pipeline_class,
        mock_create_indexer,
        runner,
        temp_index_dir,
    ):
        """Test analyze command loads index correctly."""
        # Setup mocks
        mock_indexer = Mock()
        mock_indexer.load_index.return_value = True
        mock_indexer.dependency_graph = Mock()
        mock_create_indexer.return_value = mock_indexer

        mock_pipeline = Mock()
        mock_pipeline.analyze_incremental = AsyncMock(return_value=AnalysisResult())
        mock_pipeline.analyze = AsyncMock(return_value=AnalysisResult())
        mock_pipeline.close = AsyncMock()
        mock_pipeline_class.return_value = mock_pipeline

        # Run analyze (it will fail after load because we mocked asyncio.run)
        mock_asyncio_run.return_value = AnalysisResult()

        result = runner.invoke(app, ["analyze", str(temp_index_dir)])

        # Should have called load_index
        mock_indexer.load_index.assert_called_once_with(temp_index_dir)

    def test_analyze_missing_index(self, runner, tmp_path):
        """Test analyze command with non-existent index."""
        missing_dir = tmp_path / "missing"
        result = runner.invoke(app, ["analyze", str(missing_dir)])
        # Should fail because directory doesn't exist
        assert result.exit_code != 0

    @patch("codebase_analyzer.main.create_indexer")
    def test_analyze_failed_load(self, mock_create_indexer, runner, temp_index_dir):
        """Test analyze command when index loading fails."""
        mock_indexer = Mock()
        mock_indexer.load_index.return_value = False
        mock_create_indexer.return_value = mock_indexer

        result = runner.invoke(app, ["analyze", str(temp_index_dir)])

        assert result.exit_code == 1
        assert "Failed to load index" in result.stdout


# =============================================================================
# Integration Tests
# =============================================================================


class TestCLIIntegration:
    """Integration tests for CLI workflow."""

    def test_generate_creates_complete_docs(self, runner, temp_analysis_file, temp_output_dir):
        """Test that generate creates all documentation files."""
        result = runner.invoke(
            app,
            ["generate", str(temp_analysis_file), "-o", str(temp_output_dir)],
        )
        assert result.exit_code == 0

        # Check all files created
        assert (temp_output_dir / "README.md").exists()
        assert (temp_output_dir / "STRUCTURE.md").exists()
        assert (temp_output_dir / "API.md").exists()
        assert (temp_output_dir / "modules").exists()

    def test_generate_readme_has_content(self, runner, temp_analysis_file, temp_output_dir):
        """Test that generated README has expected content."""
        runner.invoke(
            app,
            ["generate", str(temp_analysis_file), "-o", str(temp_output_dir)],
        )

        readme = (temp_output_dir / "README.md").read_text()

        assert "Overview" in readme
        assert "test application" in readme.lower()
        assert "MVC" in readme
        assert "Go" in readme

    def test_verbose_flag(self, runner, temp_analysis_file, temp_output_dir):
        """Test verbose logging flag."""
        result = runner.invoke(
            app,
            ["generate", str(temp_analysis_file), "-o", str(temp_output_dir), "-V"],
        )
        assert result.exit_code == 0


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Tests for error handling."""

    def test_invalid_analysis_json(self, runner, tmp_path, temp_output_dir):
        """Test handling of invalid JSON in analysis file."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json")

        result = runner.invoke(app, ["generate", str(bad_file), "-o", str(temp_output_dir)])
        assert result.exit_code == 1
        assert "Failed to load" in result.stdout

    def test_missing_analysis_file_in_dir(self, runner, tmp_path, temp_output_dir):
        """Test handling when analysis.json doesn't exist in directory."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        result = runner.invoke(app, ["generate", str(empty_dir), "-o", str(temp_output_dir)])
        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()
