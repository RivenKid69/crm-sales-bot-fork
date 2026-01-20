"""Tests for the analysis pipeline."""

import pytest
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from codebase_analyzer.analyzer.pipeline import AnalysisPipeline, analyze_codebase
from codebase_analyzer.analyzer.models import AnalysisResult, EntitySummary, ModuleSummary
from codebase_analyzer.indexer.graph.dependency_graph import DependencyGraph
from codebase_analyzer.indexer.models.entities import (
    FunctionEntity,
    ClassEntity,
    EntityType,
    SourceLocation,
    Language,
)
from codebase_analyzer.indexer.models.relations import Relation, RelationType


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_location_module1():
    """Location in module1."""
    return SourceLocation(
        file_path=Path("/project/src/module1/service.py"),
        start_line=1,
        end_line=20,
    )


@pytest.fixture
def sample_location_module2():
    """Location in module2."""
    return SourceLocation(
        file_path=Path("/project/src/module2/handler.py"),
        start_line=1,
        end_line=15,
    )


@pytest.fixture
def multi_module_graph(sample_location_module1, sample_location_module2):
    """Create a graph with entities in multiple modules."""
    graph = DependencyGraph()

    # Module 1: Service and Helper
    service = ClassEntity(
        id="/project/src/module1/service.py::Service",
        name="Service",
        entity_type=EntityType.CLASS,
        language=Language.TYPESCRIPT,
        location=sample_location_module1,
        source_code="class Service { ... }",
    )
    helper = FunctionEntity(
        id="/project/src/module1/service.py::helper",
        name="helper",
        entity_type=EntityType.FUNCTION,
        language=Language.TYPESCRIPT,
        location=sample_location_module1,
        source_code="def helper(): ...",
    )

    # Module 2: Handler
    handler = ClassEntity(
        id="/project/src/module2/handler.py::Handler",
        name="Handler",
        entity_type=EntityType.CLASS,
        language=Language.TYPESCRIPT,
        location=sample_location_module2,
        source_code="class Handler { ... }",
    )

    graph.add_entity(service)
    graph.add_entity(helper)
    graph.add_entity(handler)

    # Handler depends on Service
    graph.add_relation(Relation.create(
        "/project/src/module2/handler.py::Handler",
        "/project/src/module1/service.py::Service",
        RelationType.IMPORTS,
    ))

    return graph


@pytest.fixture
def mock_entity_response():
    """Mock response for entity summarization."""
    return {
        "content": json.dumps({
            "summary": "Test entity summary.",
            "purpose": "Test purpose.",
            "domain": "test",
            "key_behaviors": ["action1"],
            "dependencies_used": [],
        }),
        "input_tokens": 100,
        "output_tokens": 50,
    }


@pytest.fixture
def mock_module_response():
    """Mock response for module summarization."""
    return {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "summary": "Test module summary.",
                    "responsibilities": ["handle requests"],
                    "dependencies": ["module1"],
                    "exports": ["Handler"],
                })
            }
        }],
        "usage": {"prompt_tokens": 150, "completion_tokens": 80},
    }


@pytest.fixture
def mock_architecture_response():
    """Mock response for architecture synthesis."""
    return {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "overview": "Test system overview.",
                    "patterns_detected": ["layered"],
                    "tech_stack": ["Python"],
                    "data_flow": "Request -> Handler -> Service",
                    "key_components": ["Handler", "Service"],
                })
            }
        }],
        "usage": {"prompt_tokens": 200, "completion_tokens": 100},
    }


# ============================================================================
# Tests: Pipeline initialization
# ============================================================================

class TestPipelineInit:
    """Tests for pipeline initialization."""

    def test_init_with_defaults(self, multi_module_graph):
        """Should initialize with default settings."""
        pipeline = AnalysisPipeline(graph=multi_module_graph)

        assert pipeline.graph is multi_module_graph
        assert pipeline.api_base == "http://localhost:11434/v1"
        assert pipeline.model == "qwen3:14b"

    def test_init_with_custom_settings(self, multi_module_graph):
        """Should initialize with custom settings."""
        pipeline = AnalysisPipeline(
            graph=multi_module_graph,
            api_base="http://custom:8000/v1",
            model="custom-model",
        )

        assert pipeline.api_base == "http://custom:8000/v1"
        assert pipeline.model == "custom-model"


# ============================================================================
# Tests: Entity summarization integration
# ============================================================================

class TestEntitySummarization:
    """Tests for entity summarization stage."""

    @pytest.mark.asyncio
    async def test_summarizes_all_entities(self, multi_module_graph, mock_entity_response):
        """Should summarize all entities in the graph."""
        pipeline = AnalysisPipeline(graph=multi_module_graph)

        # Mock the summarizer's LLM call
        pipeline.summarizer._call_llm = AsyncMock(return_value=mock_entity_response)

        result = await pipeline.analyze(skip_architecture=True)

        # Should have summaries for all 3 entities
        assert len(result.entity_summaries) == 3


# ============================================================================
# Tests: Module aggregation
# ============================================================================

class TestModuleAggregation:
    """Tests for module aggregation stage."""

    @pytest.mark.asyncio
    async def test_aggregates_by_directory(self, multi_module_graph, mock_entity_response, mock_module_response):
        """Should aggregate entities by directory."""
        pipeline = AnalysisPipeline(graph=multi_module_graph)

        # Mock summarizer
        pipeline.summarizer._call_llm = AsyncMock(return_value=mock_entity_response)

        # Mock HTTP client for module/architecture calls
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=MagicMock(
            raise_for_status=MagicMock(),
            json=MagicMock(return_value=mock_module_response),
        ))
        pipeline._http_client = mock_client

        result = await pipeline.analyze(skip_architecture=True)

        # Should have module summaries
        # Module1 has 2 entities, Module2 has 1 entity
        # Only modules with >= 2 entities get summarized
        assert len(result.module_summaries) >= 1

    @pytest.mark.asyncio
    async def test_module_summary_includes_entities(self, multi_module_graph, mock_entity_response, mock_module_response):
        """Module summary should reference its entities."""
        pipeline = AnalysisPipeline(graph=multi_module_graph)
        pipeline.summarizer._call_llm = AsyncMock(return_value=mock_entity_response)

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=MagicMock(
            raise_for_status=MagicMock(),
            json=MagicMock(return_value=mock_module_response),
        ))
        pipeline._http_client = mock_client

        result = await pipeline.analyze(skip_architecture=True)

        # Check module1 has its entities
        for path, module in result.module_summaries.items():
            if "module1" in path:
                assert len(module.entities) == 2


# ============================================================================
# Tests: Architecture synthesis
# ============================================================================

class TestArchitectureSynthesis:
    """Tests for architecture synthesis stage."""

    @pytest.mark.asyncio
    async def test_synthesizes_architecture(self, multi_module_graph, mock_entity_response):
        """Should synthesize architecture from modules."""
        pipeline = AnalysisPipeline(graph=multi_module_graph)
        pipeline.summarizer._call_llm = AsyncMock(return_value=mock_entity_response)

        # Mock HTTP client that returns architecture response
        arch_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "overview": "System overview with services.",
                        "patterns_detected": ["layered"],
                        "tech_stack": ["Python"],
                        "data_flow": "A -> B",
                        "key_components": ["Service"],
                    })
                }
            }],
            "usage": {"prompt_tokens": 200, "completion_tokens": 100},
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=MagicMock(
            raise_for_status=MagicMock(),
            json=MagicMock(return_value=arch_response),
        ))
        pipeline._http_client = mock_client

        result = await pipeline.analyze(skip_architecture=False)

        # Should have architecture
        assert result.architecture is not None
        assert len(result.architecture.overview) > 0 or len(result.architecture.modules) > 0


# ============================================================================
# Tests: Full pipeline
# ============================================================================

class TestFullPipeline:
    """Tests for full pipeline execution."""

    @pytest.mark.asyncio
    async def test_full_pipeline_result(self, multi_module_graph, mock_entity_response, mock_module_response, mock_architecture_response):
        """Should produce complete analysis result."""
        pipeline = AnalysisPipeline(graph=multi_module_graph)
        pipeline.summarizer._call_llm = AsyncMock(return_value=mock_entity_response)

        # Alternate between module and architecture responses
        responses = [mock_module_response, mock_module_response, mock_architecture_response]
        response_iter = iter(responses)

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=lambda *args, **kwargs: MagicMock(
            raise_for_status=MagicMock(),
            json=MagicMock(return_value=next(response_iter, mock_architecture_response)),
        ))
        pipeline._http_client = mock_client

        result = await pipeline.analyze()

        # Check result has all components
        assert result.total_entities == 3
        assert result.processing_time_seconds > 0
        assert result.model_used == "qwen3:14b"
        assert result.analysis_timestamp != ""

    @pytest.mark.asyncio
    async def test_skip_architecture(self, multi_module_graph, mock_entity_response, mock_module_response):
        """Should skip architecture when requested."""
        pipeline = AnalysisPipeline(graph=multi_module_graph)
        pipeline.summarizer._call_llm = AsyncMock(return_value=mock_entity_response)

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=MagicMock(
            raise_for_status=MagicMock(),
            json=MagicMock(return_value=mock_module_response),
        ))
        pipeline._http_client = mock_client

        result = await pipeline.analyze(skip_architecture=True)

        assert result.architecture is None

    @pytest.mark.asyncio
    async def test_records_processing_levels(self, multi_module_graph, mock_entity_response):
        """Should record processing levels in result."""
        pipeline = AnalysisPipeline(graph=multi_module_graph)
        pipeline.summarizer._call_llm = AsyncMock(return_value=mock_entity_response)

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=MagicMock(
            raise_for_status=MagicMock(),
            json=MagicMock(return_value={"choices": [{"message": {"content": "{}"}}], "usage": {}}),
        ))
        pipeline._http_client = mock_client

        result = await pipeline.analyze(skip_architecture=True)

        assert len(result.processing_levels) > 0


# ============================================================================
# Tests: JSON parsing
# ============================================================================

class TestJsonParsing:
    """Tests for JSON response parsing."""

    def test_parse_plain_json(self, multi_module_graph):
        """Should parse plain JSON."""
        pipeline = AnalysisPipeline(graph=multi_module_graph)

        result = pipeline._parse_json_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_markdown_json(self, multi_module_graph):
        """Should parse JSON in markdown code blocks."""
        pipeline = AnalysisPipeline(graph=multi_module_graph)

        result = pipeline._parse_json_response('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_parse_invalid_json(self, multi_module_graph):
        """Should return empty dict for invalid JSON."""
        pipeline = AnalysisPipeline(graph=multi_module_graph)

        result = pipeline._parse_json_response('not valid json')
        assert result == {}


# ============================================================================
# Tests: Convenience function
# ============================================================================

class TestAnalyzeCodebase:
    """Tests for analyze_codebase convenience function."""

    @pytest.mark.asyncio
    async def test_analyze_codebase_function(self, multi_module_graph, mock_entity_response):
        """Should run full analysis via convenience function."""
        with patch.object(AnalysisPipeline, 'analyze', new_callable=AsyncMock) as mock_analyze:
            mock_analyze.return_value = AnalysisResult(
                total_entities=3,
                model_used="qwen3:14b",
            )

            result = await analyze_codebase(
                graph=multi_module_graph,
                model="qwen3:14b",
            )

            assert result.total_entities == 3
