"""Tests for topological sort and DAG processing in dependency graph."""

import pytest
from pathlib import Path

from codebase_analyzer.indexer.graph.dependency_graph import DependencyGraph
from codebase_analyzer.indexer.models.entities import (
    CodeEntity,
    EntityType,
    FunctionEntity,
    ClassEntity,
    FileEntity,
    SourceLocation,
    Language,
)
from codebase_analyzer.indexer.models.relations import Relation, RelationType

# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def empty_graph():
    """Create an empty dependency graph."""
    return DependencyGraph()

@pytest.fixture
def sample_location():
    """Create a sample source location."""
    return SourceLocation(
        file_path=Path("/test/file.py"),
        start_line=1,
        end_line=10,
    )

def create_entity(name: str, entity_type: EntityType, location: SourceLocation) -> CodeEntity:
    """Helper to create a code entity."""
    if entity_type == EntityType.FUNCTION:
        return FunctionEntity(
            id=f"test::{name}",
            name=name,
            entity_type=entity_type,
            language=Language.TYPESCRIPT,
            location=location,
        )
    elif entity_type == EntityType.CLASS:
        return ClassEntity(
            id=f"test::{name}",
            name=name,
            entity_type=entity_type,
            language=Language.TYPESCRIPT,
            location=location,
        )
    else:
        return CodeEntity(
            id=f"test::{name}",
            name=name,
            entity_type=entity_type,
            language=Language.TYPESCRIPT,
            location=location,
        )

# ============================================================================
# Tests: get_leaf_entities
# ============================================================================

class TestLeafEntities:
    """Tests for get_leaf_entities method."""

    def test_empty_graph_has_no_leaves(self, empty_graph):
        """Empty graph should have no leaves."""
        assert empty_graph.get_leaf_entities() == []

    def test_single_entity_is_leaf(self, empty_graph, sample_location):
        """Single entity with no relations is a leaf."""
        entity = create_entity("func1", EntityType.FUNCTION, sample_location)
        empty_graph.add_entity(entity)

        leaves = empty_graph.get_leaf_entities()
        assert len(leaves) == 1
        assert leaves[0] == "test::func1"

    def test_entity_with_no_outgoing_is_leaf(self, empty_graph, sample_location):
        """Entity with only incoming edges is a leaf."""
        # A calls B, so B is a leaf (no outgoing)
        a = create_entity("A", EntityType.FUNCTION, sample_location)
        b = create_entity("B", EntityType.FUNCTION, sample_location)

        empty_graph.add_entity(a)
        empty_graph.add_entity(b)
        empty_graph.add_relation(Relation.create("test::A", "test::B", RelationType.CALLS))

        leaves = empty_graph.get_leaf_entities()
        assert "test::B" in leaves
        assert "test::A" not in leaves

    def test_multiple_leaves(self, empty_graph, sample_location):
        """Multiple entities with no outgoing edges are all leaves."""
        # A calls B and C, B and C are leaves
        a = create_entity("A", EntityType.FUNCTION, sample_location)
        b = create_entity("B", EntityType.FUNCTION, sample_location)
        c = create_entity("C", EntityType.FUNCTION, sample_location)

        empty_graph.add_entity(a)
        empty_graph.add_entity(b)
        empty_graph.add_entity(c)
        empty_graph.add_relation(Relation.create("test::A", "test::B", RelationType.CALLS))
        empty_graph.add_relation(Relation.create("test::A", "test::C", RelationType.CALLS))

        leaves = empty_graph.get_leaf_entities()
        assert len(leaves) == 2
        assert "test::B" in leaves
        assert "test::C" in leaves

# ============================================================================
# Tests: find_cycles and find_strongly_connected_components
# ============================================================================

class TestCycleDetection:
    """Tests for cycle detection methods."""

    def test_no_cycles_in_dag(self, empty_graph, sample_location):
        """DAG should have no cycles."""
        # A -> B -> C (no cycles)
        a = create_entity("A", EntityType.FUNCTION, sample_location)
        b = create_entity("B", EntityType.FUNCTION, sample_location)
        c = create_entity("C", EntityType.FUNCTION, sample_location)

        empty_graph.add_entity(a)
        empty_graph.add_entity(b)
        empty_graph.add_entity(c)
        empty_graph.add_relation(Relation.create("test::A", "test::B", RelationType.CALLS))
        empty_graph.add_relation(Relation.create("test::B", "test::C", RelationType.CALLS))

        sccs = empty_graph.find_strongly_connected_components()
        # All SCCs should be size 1 (no cycles)
        assert all(len(scc) == 1 for scc in sccs) or len(sccs) == 0

    def test_simple_cycle_detected(self, empty_graph, sample_location):
        """Simple A -> B -> A cycle should be detected."""
        a = create_entity("A", EntityType.FUNCTION, sample_location)
        b = create_entity("B", EntityType.FUNCTION, sample_location)

        empty_graph.add_entity(a)
        empty_graph.add_entity(b)
        empty_graph.add_relation(Relation.create("test::A", "test::B", RelationType.CALLS))
        empty_graph.add_relation(Relation.create("test::B", "test::A", RelationType.CALLS))

        sccs = empty_graph.find_strongly_connected_components()
        # Should have one SCC with 2 nodes
        assert len(sccs) == 1
        assert len(sccs[0]) == 2
        assert "test::A" in sccs[0]
        assert "test::B" in sccs[0]

    def test_complex_cycle_detected(self, empty_graph, sample_location):
        """Complex cycle A -> B -> C -> A should be detected."""
        a = create_entity("A", EntityType.FUNCTION, sample_location)
        b = create_entity("B", EntityType.FUNCTION, sample_location)
        c = create_entity("C", EntityType.FUNCTION, sample_location)

        empty_graph.add_entity(a)
        empty_graph.add_entity(b)
        empty_graph.add_entity(c)
        empty_graph.add_relation(Relation.create("test::A", "test::B", RelationType.CALLS))
        empty_graph.add_relation(Relation.create("test::B", "test::C", RelationType.CALLS))
        empty_graph.add_relation(Relation.create("test::C", "test::A", RelationType.CALLS))

        sccs = empty_graph.find_strongly_connected_components()
        assert len(sccs) == 1
        assert len(sccs[0]) == 3

# ============================================================================
# Tests: break_cycles
# ============================================================================

class TestBreakCycles:
    """Tests for cycle breaking functionality."""

    def test_break_simple_cycle(self, empty_graph, sample_location):
        """Should break simple A -> B -> A cycle."""
        a = create_entity("A", EntityType.FUNCTION, sample_location)
        b = create_entity("B", EntityType.FUNCTION, sample_location)

        empty_graph.add_entity(a)
        empty_graph.add_entity(b)
        empty_graph.add_relation(Relation.create("test::A", "test::B", RelationType.CALLS))
        empty_graph.add_relation(Relation.create("test::B", "test::A", RelationType.CALLS))

        removed = empty_graph.break_cycles()

        # One edge should be removed
        assert len(removed) >= 1
        # Graph should now be acyclic
        sccs = empty_graph.find_strongly_connected_components()
        assert len(sccs) == 0  # No SCCs with size > 1

    def test_break_cycle_removes_minimum_weight(self, empty_graph, sample_location):
        """Should prefer removing lower weight edges."""
        a = create_entity("A", EntityType.FUNCTION, sample_location)
        b = create_entity("B", EntityType.FUNCTION, sample_location)

        empty_graph.add_entity(a)
        empty_graph.add_entity(b)

        # Add edges with different weights
        rel1 = Relation.create("test::A", "test::B", RelationType.CALLS)
        rel1.weight = 10.0  # High weight - should keep
        rel2 = Relation.create("test::B", "test::A", RelationType.CALLS)
        rel2.weight = 1.0  # Low weight - should remove

        empty_graph.add_relation(rel1)
        empty_graph.add_relation(rel2)

        removed = empty_graph.break_cycles()

        # Should remove the lower weight edge (B -> A)
        assert len(removed) == 1
        assert removed[0][0] == "test::B"
        assert removed[0][1] == "test::A"

# ============================================================================
# Tests: get_topological_order
# ============================================================================

class TestTopologicalOrder:
    """Tests for topological ordering."""

    def test_empty_graph(self, empty_graph):
        """Empty graph should return empty order."""
        order = empty_graph.get_topological_order()
        assert order == []

    def test_single_entity(self, empty_graph, sample_location):
        """Single entity should be in order."""
        entity = create_entity("A", EntityType.FUNCTION, sample_location)
        empty_graph.add_entity(entity)

        order = empty_graph.get_topological_order()
        assert order == ["test::A"]

    def test_linear_chain(self, empty_graph, sample_location):
        """Linear chain A -> B -> C should have C first (leaf)."""
        a = create_entity("A", EntityType.FUNCTION, sample_location)
        b = create_entity("B", EntityType.FUNCTION, sample_location)
        c = create_entity("C", EntityType.FUNCTION, sample_location)

        empty_graph.add_entity(a)
        empty_graph.add_entity(b)
        empty_graph.add_entity(c)
        empty_graph.add_relation(Relation.create("test::A", "test::B", RelationType.CALLS))
        empty_graph.add_relation(Relation.create("test::B", "test::C", RelationType.CALLS))

        order = empty_graph.get_topological_order()

        # C should come before B, B before A (bottom-up)
        assert order.index("test::C") < order.index("test::B")
        assert order.index("test::B") < order.index("test::A")

    def test_diamond_dependency(self, empty_graph, sample_location):
        """Diamond: A -> B, A -> C, B -> D, C -> D."""
        a = create_entity("A", EntityType.FUNCTION, sample_location)
        b = create_entity("B", EntityType.FUNCTION, sample_location)
        c = create_entity("C", EntityType.FUNCTION, sample_location)
        d = create_entity("D", EntityType.FUNCTION, sample_location)

        empty_graph.add_entity(a)
        empty_graph.add_entity(b)
        empty_graph.add_entity(c)
        empty_graph.add_entity(d)
        empty_graph.add_relation(Relation.create("test::A", "test::B", RelationType.CALLS))
        empty_graph.add_relation(Relation.create("test::A", "test::C", RelationType.CALLS))
        empty_graph.add_relation(Relation.create("test::B", "test::D", RelationType.CALLS))
        empty_graph.add_relation(Relation.create("test::C", "test::D", RelationType.CALLS))

        order = empty_graph.get_topological_order()

        # D should come first (leaf), A should come last
        assert order.index("test::D") < order.index("test::B")
        assert order.index("test::D") < order.index("test::C")
        assert order.index("test::B") < order.index("test::A")
        assert order.index("test::C") < order.index("test::A")

# ============================================================================
# Tests: get_processing_levels
# ============================================================================

class TestProcessingLevels:
    """Tests for processing levels (parallel execution groups)."""

    def test_empty_graph(self, empty_graph):
        """Empty graph should return empty levels."""
        levels = empty_graph.get_processing_levels()
        assert levels == []

    def test_single_entity(self, empty_graph, sample_location):
        """Single entity should be in one level."""
        entity = create_entity("A", EntityType.FUNCTION, sample_location)
        empty_graph.add_entity(entity)

        levels = empty_graph.get_processing_levels()
        assert len(levels) == 1
        assert levels[0] == ["test::A"]

    def test_independent_entities(self, empty_graph, sample_location):
        """Independent entities should all be in level 0."""
        a = create_entity("A", EntityType.FUNCTION, sample_location)
        b = create_entity("B", EntityType.FUNCTION, sample_location)
        c = create_entity("C", EntityType.FUNCTION, sample_location)

        empty_graph.add_entity(a)
        empty_graph.add_entity(b)
        empty_graph.add_entity(c)
        # No relations - all independent

        levels = empty_graph.get_processing_levels()
        assert len(levels) == 1
        assert len(levels[0]) == 3

    def test_linear_chain_levels(self, empty_graph, sample_location):
        """Linear chain A -> B -> C should have 3 levels."""
        a = create_entity("A", EntityType.FUNCTION, sample_location)
        b = create_entity("B", EntityType.FUNCTION, sample_location)
        c = create_entity("C", EntityType.FUNCTION, sample_location)

        empty_graph.add_entity(a)
        empty_graph.add_entity(b)
        empty_graph.add_entity(c)
        empty_graph.add_relation(Relation.create("test::A", "test::B", RelationType.CALLS))
        empty_graph.add_relation(Relation.create("test::B", "test::C", RelationType.CALLS))

        levels = empty_graph.get_processing_levels()

        assert len(levels) == 3
        # Level 0: C (no deps)
        assert "test::C" in levels[0]
        # Level 1: B (depends on C)
        assert "test::B" in levels[1]
        # Level 2: A (depends on B)
        assert "test::A" in levels[2]

    def test_diamond_levels(self, empty_graph, sample_location):
        """Diamond pattern should have 3 levels with parallel middle."""
        a = create_entity("A", EntityType.FUNCTION, sample_location)
        b = create_entity("B", EntityType.FUNCTION, sample_location)
        c = create_entity("C", EntityType.FUNCTION, sample_location)
        d = create_entity("D", EntityType.FUNCTION, sample_location)

        empty_graph.add_entity(a)
        empty_graph.add_entity(b)
        empty_graph.add_entity(c)
        empty_graph.add_entity(d)
        empty_graph.add_relation(Relation.create("test::A", "test::B", RelationType.CALLS))
        empty_graph.add_relation(Relation.create("test::A", "test::C", RelationType.CALLS))
        empty_graph.add_relation(Relation.create("test::B", "test::D", RelationType.CALLS))
        empty_graph.add_relation(Relation.create("test::C", "test::D", RelationType.CALLS))

        levels = empty_graph.get_processing_levels()

        assert len(levels) == 3
        # Level 0: D
        assert levels[0] == ["test::D"]
        # Level 1: B and C (can be parallel)
        assert len(levels[1]) == 2
        assert "test::B" in levels[1]
        assert "test::C" in levels[1]
        # Level 2: A
        assert levels[2] == ["test::A"]

    def test_handles_cycles(self, empty_graph, sample_location):
        """Should handle cycles gracefully."""
        a = create_entity("A", EntityType.FUNCTION, sample_location)
        b = create_entity("B", EntityType.FUNCTION, sample_location)

        empty_graph.add_entity(a)
        empty_graph.add_entity(b)
        empty_graph.add_relation(Relation.create("test::A", "test::B", RelationType.CALLS))
        empty_graph.add_relation(Relation.create("test::B", "test::A", RelationType.CALLS))

        # Should not raise, should handle cycle
        levels = empty_graph.get_processing_levels()

        # Both entities should be accounted for
        all_entities = [e for level in levels for e in level]
        assert "test::A" in all_entities
        assert "test::B" in all_entities

# ============================================================================
# Tests: get_dependency_ids and get_dependent_ids
# ============================================================================

class TestDependencyHelpers:
    """Tests for dependency helper methods."""

    def test_get_dependency_ids(self, empty_graph, sample_location):
        """get_dependency_ids should return IDs of dependencies."""
        a = create_entity("A", EntityType.FUNCTION, sample_location)
        b = create_entity("B", EntityType.FUNCTION, sample_location)
        c = create_entity("C", EntityType.FUNCTION, sample_location)

        empty_graph.add_entity(a)
        empty_graph.add_entity(b)
        empty_graph.add_entity(c)
        empty_graph.add_relation(Relation.create("test::A", "test::B", RelationType.CALLS))
        empty_graph.add_relation(Relation.create("test::A", "test::C", RelationType.CALLS))

        deps = empty_graph.get_dependency_ids("test::A")
        assert len(deps) == 2
        assert "test::B" in deps
        assert "test::C" in deps

        # B has no dependencies
        assert empty_graph.get_dependency_ids("test::B") == []

    def test_get_dependent_ids(self, empty_graph, sample_location):
        """get_dependent_ids should return IDs of dependents."""
        a = create_entity("A", EntityType.FUNCTION, sample_location)
        b = create_entity("B", EntityType.FUNCTION, sample_location)

        empty_graph.add_entity(a)
        empty_graph.add_entity(b)
        empty_graph.add_relation(Relation.create("test::A", "test::B", RelationType.CALLS))

        # B is depended on by A
        dependents = empty_graph.get_dependent_ids("test::B")
        assert dependents == ["test::A"]

        # A has no dependents
        assert empty_graph.get_dependent_ids("test::A") == []

    def test_nonexistent_entity(self, empty_graph):
        """Should return empty list for nonexistent entity."""
        assert empty_graph.get_dependency_ids("nonexistent") == []
        assert empty_graph.get_dependent_ids("nonexistent") == []
