"""Tests for EntitySummarizer with mocked LLM responses."""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import json

from codebase_analyzer.analyzer.summarizer import EntitySummarizer, SUMMARIZER_SYSTEM_PROMPT
from codebase_analyzer.analyzer.models import EntitySummary
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
def sample_location():
    """Create a sample source location."""
    return SourceLocation(
        file_path=Path("/test/file.py"),
        start_line=1,
        end_line=20,
    )

@pytest.fixture
def sample_function(sample_location):
    """Create a sample function entity."""
    return FunctionEntity(
        id="test/file.py::calculate_total",
        name="calculate_total",
        entity_type=EntityType.FUNCTION,
        language=Language.TYPESCRIPT,
        location=sample_location,
        source_code="""
def calculate_total(items: list[Item], discount: float = 0.0) -> float:
    \"\"\"Calculate total price with optional discount.\"\"\"
    subtotal = sum(item.price * item.quantity for item in items)
    return subtotal * (1 - discount)
""",
    )

@pytest.fixture
def sample_class(sample_location):
    """Create a sample class entity."""
    return ClassEntity(
        id="test/file.py::OrderService",
        name="OrderService",
        entity_type=EntityType.CLASS,
        language=Language.TYPESCRIPT,
        location=sample_location,
        source_code="""
class OrderService:
    \"\"\"Manages order lifecycle.\"\"\"

    def __init__(self, db: Database):
        self.db = db

    def create_order(self, user_id: str, items: list[Item]) -> Order:
        order = Order(user_id=user_id, items=items)
        self.db.save(order)
        return order
""",
    )

@pytest.fixture
def mock_llm_response():
    """Create a mock LLM response."""
    return {
        "content": json.dumps({
            "summary": "Calculates total price for a list of items with optional discount.",
            "purpose": "Compute order totals for checkout.",
            "domain": "payments",
            "key_behaviors": ["sum_prices", "apply_discount"],
            "dependencies_used": ["Item"],
        }),
        "input_tokens": 100,
        "output_tokens": 50,
    }

# ============================================================================
# Tests: Basic functionality
# ============================================================================

class TestEntitySummarizerBasic:
    """Basic tests for EntitySummarizer."""

    def test_init(self):
        """Should initialize with default settings."""
        summarizer = EntitySummarizer()
        assert summarizer.api_base == "http://localhost:11434/v1"
        assert summarizer.model == "qwen3:14b"
        assert summarizer._summaries == {}

    def test_get_code_hash(self, sample_function):
        """Should compute consistent hash for source code."""
        summarizer = EntitySummarizer()

        hash1 = summarizer.get_code_hash(sample_function)
        hash2 = summarizer.get_code_hash(sample_function)

        assert hash1 == hash2
        assert len(hash1) == 16  # Truncated SHA256

    def test_get_code_hash_ignores_whitespace(self, sample_location):
        """Hash should be same for code differing only in whitespace."""
        summarizer = EntitySummarizer()

        func1 = FunctionEntity(
            id="test::func",
            name="func",
            entity_type=EntityType.FUNCTION,
            language=Language.TYPESCRIPT,
            location=sample_location,
            source_code="def foo():  return 1",
        )

        func2 = FunctionEntity(
            id="test::func",
            name="func",
            entity_type=EntityType.FUNCTION,
            language=Language.TYPESCRIPT,
            location=sample_location,
            source_code="def foo():    return    1",
        )

        assert summarizer.get_code_hash(func1) == summarizer.get_code_hash(func2)

    def test_build_context_empty(self):
        """Should handle empty dependencies."""
        summarizer = EntitySummarizer()
        context = summarizer._build_context([])
        assert context == "No internal dependencies."

    def test_build_context_with_deps(self):
        """Should build context from dependency summaries."""
        summarizer = EntitySummarizer()

        dep_summaries = [
            EntitySummary(
                entity_id="src/db.py::Database",
                summary="Database connection manager.",
                purpose="Manages PostgreSQL connections.",
                domain="database",
            ),
            EntitySummary(
                entity_id="src/models.py::Order",
                summary="Order data model.",
                purpose="Represents a customer order.",
                domain="models",
            ),
        ]

        context = summarizer._build_context(dep_summaries)

        assert "Dependencies:" in context
        assert "src/db.py::Database" in context
        assert "Manages PostgreSQL connections" in context
        assert "src/models.py::Order" in context

    def test_build_context_limits_deps(self):
        """Should limit number of dependencies in context."""
        summarizer = EntitySummarizer()

        # Create 20 dependencies
        dep_summaries = [
            EntitySummary(
                entity_id=f"dep{i}",
                summary=f"Summary {i}",
                purpose=f"Purpose {i}",
                domain="test",
            )
            for i in range(20)
        ]

        context = summarizer._build_context(dep_summaries)

        # Should only include first 15
        assert "dep0" in context
        assert "dep14" in context
        # dep15 and beyond should not be included
        lines = context.split("\n")
        assert len(lines) <= 16  # "Dependencies:" + 15 deps

# ============================================================================
# Tests: LLM interaction (mocked)
# ============================================================================

class TestEntitySummarizerWithMock:
    """Tests with mocked LLM responses."""

    @pytest.mark.asyncio
    async def test_summarize_entity(self, sample_function, mock_llm_response):
        """Should summarize an entity using LLM."""
        summarizer = EntitySummarizer()

        # Mock the _call_llm method
        summarizer._call_llm = AsyncMock(return_value=mock_llm_response)

        summary = await summarizer.summarize_entity(sample_function)

        assert summary.entity_id == sample_function.id
        assert "total price" in summary.summary.lower()
        assert summary.domain == "payments"
        assert "sum_prices" in summary.key_behaviors
        assert summary.input_tokens == 100
        assert summary.output_tokens == 50

    @pytest.mark.asyncio
    async def test_summarize_entity_with_deps(self, sample_function, mock_llm_response):
        """Should include dependency context when summarizing."""
        summarizer = EntitySummarizer()
        summarizer._call_llm = AsyncMock(return_value=mock_llm_response)

        dep_summaries = [
            EntitySummary(
                entity_id="models::Item",
                summary="Product item.",
                purpose="Represents a product item.",
                domain="models",
            ),
        ]

        summary = await summarizer.summarize_entity(sample_function, dep_summaries)

        # Verify _call_llm was called with prompt containing dependency
        call_args = summarizer._call_llm.call_args[0][0]  # First positional arg
        assert "models::Item" in call_args
        assert "Dependencies:" in call_args

    @pytest.mark.asyncio
    async def test_summarize_entity_caches_result(self, sample_function, mock_llm_response):
        """Should cache and return cached summaries."""
        summarizer = EntitySummarizer()
        summarizer._call_llm = AsyncMock(return_value=mock_llm_response)

        # First call
        summary1 = await summarizer.summarize_entity(sample_function)
        assert summarizer._call_llm.call_count == 1

        # Second call should use cache
        summary2 = await summarizer.summarize_entity(sample_function)
        assert summarizer._call_llm.call_count == 1  # Not called again

        assert summary1.entity_id == summary2.entity_id

    @pytest.mark.asyncio
    async def test_parse_response_handles_markdown(self, sample_function):
        """Should parse JSON from markdown code blocks."""
        summarizer = EntitySummarizer()

        # Response wrapped in markdown
        markdown_response = {
            "content": """```json
{
    "summary": "Test summary",
    "purpose": "Test purpose",
    "domain": "test",
    "key_behaviors": [],
    "dependencies_used": []
}
```""",
            "input_tokens": 50,
            "output_tokens": 30,
        }

        summarizer._call_llm = AsyncMock(return_value=markdown_response)
        summary = await summarizer.summarize_entity(sample_function)

        assert summary.summary == "Test summary"
        assert summary.purpose == "Test purpose"

    @pytest.mark.asyncio
    async def test_parse_response_handles_invalid_json(self, sample_function):
        """Should handle invalid JSON gracefully."""
        summarizer = EntitySummarizer()

        invalid_response = {
            "content": "This is not valid JSON at all",
            "input_tokens": 50,
            "output_tokens": 30,
        }

        summarizer._call_llm = AsyncMock(return_value=invalid_response)
        summary = await summarizer.summarize_entity(sample_function)

        # Should create fallback summary
        assert summary.entity_id == sample_function.id
        assert sample_function.name in summary.summary
        assert summary.domain == "unknown"

# ============================================================================
# Tests: Level-based summarization
# ============================================================================

class TestLevelSummarization:
    """Tests for summarize_level functionality."""

    @pytest.fixture
    def sample_graph(self, sample_location):
        """Create a sample graph with entities."""
        graph = DependencyGraph()

        # Create entities
        func_a = FunctionEntity(
            id="test::A",
            name="A",
            entity_type=EntityType.FUNCTION,
            language=Language.TYPESCRIPT,
            location=sample_location,
            source_code="def A(): return B()",
        )
        func_b = FunctionEntity(
            id="test::B",
            name="B",
            entity_type=EntityType.FUNCTION,
            language=Language.TYPESCRIPT,
            location=sample_location,
            source_code="def B(): return 1",
        )

        graph.add_entity(func_a)
        graph.add_entity(func_b)
        graph.add_relation(Relation.create("test::A", "test::B", RelationType.CALLS))

        return graph

    @pytest.mark.asyncio
    async def test_summarize_level(self, sample_graph, mock_llm_response):
        """Should summarize all entities at a level."""
        summarizer = EntitySummarizer()
        summarizer._call_llm = AsyncMock(return_value=mock_llm_response)

        # Level 0 should have B (leaf)
        level_0 = ["test::B"]
        summaries = await summarizer.summarize_level(level_0, sample_graph)

        assert len(summaries) == 1
        assert summaries[0].entity_id == "test::B"

    @pytest.mark.asyncio
    async def test_summarize_level_uses_previous_summaries(self, sample_graph):
        """Should use summaries from previous levels as context."""
        summarizer = EntitySummarizer()

        # First summarize B
        b_response = {
            "content": json.dumps({
                "summary": "Returns 1",
                "purpose": "Constant function",
                "domain": "utils",
                "key_behaviors": [],
                "dependencies_used": [],
            }),
            "input_tokens": 50,
            "output_tokens": 30,
        }
        summarizer._call_llm = AsyncMock(return_value=b_response)
        await summarizer.summarize_level(["test::B"], sample_graph)

        # Now summarize A (depends on B)
        a_response = {
            "content": json.dumps({
                "summary": "Calls B",
                "purpose": "Wrapper for B",
                "domain": "utils",
                "key_behaviors": ["call_b"],
                "dependencies_used": ["B"],
            }),
            "input_tokens": 60,
            "output_tokens": 35,
        }
        summarizer._call_llm = AsyncMock(return_value=a_response)
        await summarizer.summarize_level(["test::A"], sample_graph)

        # Verify A's summary includes B as dependency
        a_summary = summarizer.get_cached_summary("test::A")
        assert a_summary is not None
        assert "B" in a_summary.dependencies_used

    @pytest.mark.asyncio
    async def test_summarize_level_handles_missing_entities(self, sample_graph, mock_llm_response):
        """Should handle missing entities gracefully."""
        summarizer = EntitySummarizer()
        summarizer._call_llm = AsyncMock(return_value=mock_llm_response)

        # Include non-existent entity
        level = ["test::B", "nonexistent"]
        summaries = await summarizer.summarize_level(level, sample_graph)

        # Should only have B
        assert len(summaries) == 1
        assert summaries[0].entity_id == "test::B"

# ============================================================================
# Tests: Full summarization
# ============================================================================

class TestFullSummarization:
    """Tests for summarize_all functionality."""

    @pytest.fixture
    def diamond_graph(self, sample_location):
        """Create a diamond-shaped dependency graph."""
        graph = DependencyGraph()

        # A depends on B and C, B and C depend on D
        for name in ["A", "B", "C", "D"]:
            entity = FunctionEntity(
                id=f"test::{name}",
                name=name,
                entity_type=EntityType.FUNCTION,
                language=Language.TYPESCRIPT,
                location=sample_location,
                source_code=f"def {name}(): pass",
            )
            graph.add_entity(entity)

        graph.add_relation(Relation.create("test::A", "test::B", RelationType.CALLS))
        graph.add_relation(Relation.create("test::A", "test::C", RelationType.CALLS))
        graph.add_relation(Relation.create("test::B", "test::D", RelationType.CALLS))
        graph.add_relation(Relation.create("test::C", "test::D", RelationType.CALLS))

        return graph

    @pytest.mark.asyncio
    async def test_summarize_all(self, diamond_graph, mock_llm_response):
        """Should summarize all entities in bottom-up order."""
        summarizer = EntitySummarizer()
        summarizer._call_llm = AsyncMock(return_value=mock_llm_response)

        all_summaries = await summarizer.summarize_all(diamond_graph)

        assert len(all_summaries) == 4
        assert "test::A" in all_summaries
        assert "test::D" in all_summaries

    @pytest.mark.asyncio
    async def test_summarize_all_processes_bottom_up(self, diamond_graph):
        """Should process in bottom-up order (D before B/C before A)."""
        summarizer = EntitySummarizer()

        call_order = []

        async def mock_call_llm(prompt):
            # Extract entity name from prompt
            for name in ["A", "B", "C", "D"]:
                if f"def {name}" in prompt:
                    call_order.append(name)
                    break
            return {
                "content": json.dumps({
                    "summary": "Test",
                    "purpose": "Test",
                    "domain": "test",
                    "key_behaviors": [],
                    "dependencies_used": [],
                }),
                "input_tokens": 50,
                "output_tokens": 30,
            }

        summarizer._call_llm = mock_call_llm

        await summarizer.summarize_all(diamond_graph)

        # D should be processed first (leaf)
        assert call_order[0] == "D"
        # A should be processed last (root)
        assert call_order[-1] == "A"
        # B and C should be between D and A
        assert "B" in call_order[1:3]
        assert "C" in call_order[1:3]

    @pytest.mark.asyncio
    async def test_clear_cache(self, sample_function, mock_llm_response):
        """Should clear cached summaries."""
        summarizer = EntitySummarizer()
        summarizer._call_llm = AsyncMock(return_value=mock_llm_response)

        await summarizer.summarize_entity(sample_function)
        assert len(summarizer._summaries) == 1

        summarizer.clear_cache()
        assert len(summarizer._summaries) == 0
