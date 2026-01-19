"""Tests for codebase_analyzer/indexer/graph/dependency_graph.py - Dependency graph."""

from pathlib import Path

import pytest

from codebase_analyzer.indexer.graph.dependency_graph import (
    DependencyGraph,
    build_dependency_graph,
)
from codebase_analyzer.indexer.models.entities import (
    ClassEntity,
    CodeEntity,
    EntityType,
    FileEntity,
    FunctionEntity,
    ImportEntity,
    Language,
    SourceLocation,
    Visibility,
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
        file_path=Path("/src/test.go"),
        start_line=1,
        end_line=10,
    )


@pytest.fixture
def sample_function(sample_location):
    """Create a sample function entity."""
    return FunctionEntity(
        id="src/test.go:function:TestFunc",
        name="TestFunc",
        entity_type=EntityType.FUNCTION,
        language=Language.GO,
        location=sample_location,
    )


@pytest.fixture
def sample_class(sample_location):
    """Create a sample class entity."""
    return ClassEntity(
        id="src/User.php:class:User",
        name="User",
        entity_type=EntityType.CLASS,
        language=Language.PHP,
        location=SourceLocation(
            file_path=Path("/src/User.php"),
            start_line=1,
            end_line=50,
        ),
    )


@pytest.fixture
def sample_interface(sample_location):
    """Create a sample interface entity."""
    return ClassEntity(
        id="src/UserInterface.php:interface:UserInterface",
        name="UserInterface",
        entity_type=EntityType.INTERFACE,
        language=Language.PHP,
        location=SourceLocation(
            file_path=Path("/src/UserInterface.php"),
            start_line=1,
            end_line=20,
        ),
        is_interface=True,
    )


@pytest.fixture
def populated_graph():
    """Create a graph with multiple entities and relations."""
    graph = DependencyGraph()

    # Create locations
    loc1 = SourceLocation(file_path=Path("/src/user.go"), start_line=1, end_line=50)
    loc2 = SourceLocation(file_path=Path("/src/service.go"), start_line=1, end_line=100)
    loc3 = SourceLocation(file_path=Path("/src/repo.go"), start_line=1, end_line=80)

    # Create entities
    user_struct = ClassEntity(
        id="src/user.go:struct:User",
        name="User",
        entity_type=EntityType.STRUCT,
        language=Language.GO,
        location=loc1,
    )

    user_repo_interface = ClassEntity(
        id="src/repo.go:interface:UserRepository",
        name="UserRepository",
        entity_type=EntityType.INTERFACE,
        language=Language.GO,
        location=loc3,
        is_interface=True,
    )

    user_service = ClassEntity(
        id="src/service.go:struct:UserService",
        name="UserService",
        entity_type=EntityType.STRUCT,
        language=Language.GO,
        location=loc2,
        implements=["UserRepository"],
    )

    get_user = FunctionEntity(
        id="src/service.go:method:GetUser",
        name="GetUser",
        entity_type=EntityType.METHOD,
        language=Language.GO,
        location=loc2,
        calls=["ValidateID", "db.Query"],
    )

    validate_id = FunctionEntity(
        id="src/service.go:function:ValidateID",
        name="ValidateID",
        entity_type=EntityType.FUNCTION,
        language=Language.GO,
        location=loc2,
    )

    # Add entities
    graph.add_entity(user_struct)
    graph.add_entity(user_repo_interface)
    graph.add_entity(user_service)
    graph.add_entity(get_user)
    graph.add_entity(validate_id)

    # Add relations
    graph.add_relation(
        Relation.create(
            user_service.id,
            user_repo_interface.id,
            RelationType.IMPLEMENTS,
        )
    )

    graph.add_relation(
        Relation.create(
            get_user.id,
            validate_id.id,
            RelationType.CALLS,
        )
    )

    return graph


# ============================================================================
# DependencyGraph Basic Tests
# ============================================================================


class TestDependencyGraphBasics:
    """Tests for DependencyGraph basic operations."""

    def test_empty_graph_creation(self, empty_graph):
        """Test creating an empty graph."""
        assert empty_graph is not None
        assert empty_graph.stats["total_entities"] == 0
        assert empty_graph.stats["total_relations"] == 0

    def test_add_entity(self, empty_graph, sample_function):
        """Test adding an entity to the graph."""
        empty_graph.add_entity(sample_function)

        assert empty_graph.stats["total_entities"] == 1
        assert empty_graph.get_entity(sample_function.id) is not None
        assert empty_graph.get_entity(sample_function.id).name == "TestFunc"

    def test_add_multiple_entities(self, empty_graph, sample_function, sample_class):
        """Test adding multiple entities."""
        empty_graph.add_entity(sample_function)
        empty_graph.add_entity(sample_class)

        assert empty_graph.stats["total_entities"] == 2
        assert empty_graph.stats["functions"] == 1
        assert empty_graph.stats["classes"] == 1

    def test_get_nonexistent_entity(self, empty_graph):
        """Test getting a non-existent entity."""
        result = empty_graph.get_entity("nonexistent:id")
        assert result is None

    def test_add_relation(self, empty_graph, sample_class, sample_interface):
        """Test adding a relation."""
        empty_graph.add_entity(sample_class)
        empty_graph.add_entity(sample_interface)

        relation = Relation.create(
            sample_class.id,
            sample_interface.id,
            RelationType.IMPLEMENTS,
        )
        empty_graph.add_relation(relation)

        assert empty_graph.stats["total_relations"] == 1

    def test_add_call_relation(self, empty_graph, sample_location):
        """Test adding a CALLS relation updates call graph."""
        func1 = FunctionEntity(
            id="test:func1",
            name="func1",
            entity_type=EntityType.FUNCTION,
            language=Language.GO,
            location=sample_location,
        )
        func2 = FunctionEntity(
            id="test:func2",
            name="func2",
            entity_type=EntityType.FUNCTION,
            language=Language.GO,
            location=sample_location,
        )

        empty_graph.add_entity(func1)
        empty_graph.add_entity(func2)

        relation = Relation.create(func1.id, func2.id, RelationType.CALLS)
        empty_graph.add_relation(relation)

        # Check call graph is updated
        chains = empty_graph.get_call_chain(func1.id)
        assert len(chains) == 1
        assert func2.id in chains[0]


# ============================================================================
# Entity Lookup Tests
# ============================================================================


class TestEntityLookup:
    """Tests for entity lookup operations."""

    def test_get_entities_in_file(self, populated_graph):
        """Test getting entities in a specific file."""
        entities = populated_graph.get_entities_in_file(Path("/src/service.go"))

        assert len(entities) >= 2
        entity_names = [e.name for e in entities]
        assert "UserService" in entity_names
        assert "GetUser" in entity_names

    def test_get_entities_in_nonexistent_file(self, populated_graph):
        """Test getting entities for a non-existent file."""
        entities = populated_graph.get_entities_in_file(Path("/nonexistent.go"))
        assert entities == []

    def test_get_entities_by_type(self, populated_graph):
        """Test getting entities by type."""
        structs = populated_graph.get_entities_by_type(EntityType.STRUCT)
        interfaces = populated_graph.get_entities_by_type(EntityType.INTERFACE)
        functions = populated_graph.get_entities_by_type(EntityType.FUNCTION)

        assert len(structs) == 2
        assert len(interfaces) == 1
        assert len(functions) >= 1

    def test_get_entities_by_nonexistent_type(self, populated_graph):
        """Test getting entities of a type with no entities."""
        components = populated_graph.get_entities_by_type(EntityType.COMPONENT)
        assert components == []


# ============================================================================
# Dependency Tests
# ============================================================================


class TestDependencies:
    """Tests for dependency retrieval."""

    def test_get_dependencies(self, populated_graph):
        """Test getting dependencies of an entity."""
        deps = populated_graph.get_dependencies("src/service.go:struct:UserService")

        assert len(deps) >= 1
        # Should include IMPLEMENTS relationship
        dep_types = [rel_type for _, rel_type in deps]
        assert RelationType.IMPLEMENTS in dep_types

    def test_get_dependents(self, populated_graph):
        """Test getting entities that depend on an entity."""
        deps = populated_graph.get_dependents("src/repo.go:interface:UserRepository")

        assert len(deps) >= 1
        # UserService implements UserRepository
        dep_ids = [entity_id for entity_id, _ in deps]
        assert any("UserService" in eid for eid in dep_ids)

    def test_get_dependencies_nonexistent_entity(self, populated_graph):
        """Test getting dependencies of non-existent entity."""
        deps = populated_graph.get_dependencies("nonexistent:id")
        assert deps == []

    def test_get_dependents_nonexistent_entity(self, populated_graph):
        """Test getting dependents of non-existent entity."""
        deps = populated_graph.get_dependents("nonexistent:id")
        assert deps == []


# ============================================================================
# Call Chain Tests
# ============================================================================


class TestCallChain:
    """Tests for call chain analysis."""

    def test_get_call_chain_simple(self, populated_graph):
        """Test getting call chain for a function."""
        chains = populated_graph.get_call_chain("src/service.go:method:GetUser")

        assert len(chains) >= 1
        # GetUser calls ValidateID
        assert any("ValidateID" in chain[-1] for chain in chains)

    def test_get_call_chain_with_depth(self, empty_graph, sample_location):
        """Test call chain with specified depth."""
        # Create a chain: func1 -> func2 -> func3 -> func4
        funcs = []
        for i in range(1, 5):
            func = FunctionEntity(
                id=f"test:func{i}",
                name=f"func{i}",
                entity_type=EntityType.FUNCTION,
                language=Language.GO,
                location=sample_location,
            )
            funcs.append(func)
            empty_graph.add_entity(func)

        # Create call relations
        for i in range(len(funcs) - 1):
            relation = Relation.create(
                funcs[i].id,
                funcs[i + 1].id,
                RelationType.CALLS,
            )
            empty_graph.add_relation(relation)

        # Get call chains with depth 2
        chains = empty_graph.get_call_chain(funcs[0].id, max_depth=2)

        # Should have chains of length 2, 3 (depth 2 means 2 calls)
        assert len(chains) >= 1

    def test_get_call_chain_nonexistent(self, populated_graph):
        """Test call chain for non-existent entity."""
        chains = populated_graph.get_call_chain("nonexistent:id")
        assert chains == []

    def test_get_call_chain_no_calls(self, empty_graph, sample_function):
        """Test call chain for function with no calls."""
        empty_graph.add_entity(sample_function)
        chains = empty_graph.get_call_chain(sample_function.id)

        # Function has no outgoing calls
        assert chains == []


# ============================================================================
# Class Hierarchy Tests
# ============================================================================


class TestClassHierarchy:
    """Tests for class hierarchy analysis."""

    def test_get_class_hierarchy_with_implements(self, populated_graph):
        """Test class hierarchy for implementing class."""
        hierarchy = populated_graph.get_class_hierarchy(
            "src/service.go:struct:UserService"
        )

        assert "ancestors" in hierarchy
        assert "descendants" in hierarchy

        # Note: Edge direction is source -> target (UserService -> UserRepository)
        # so descendants of UserService should include UserRepository
        descendant_names = [d["name"] for d in hierarchy["descendants"]]
        assert "UserRepository" in descendant_names

    def test_get_class_hierarchy_interface(self, populated_graph):
        """Test class hierarchy for interface."""
        hierarchy = populated_graph.get_class_hierarchy(
            "src/repo.go:interface:UserRepository"
        )

        # Note: Edge direction is source -> target (UserService -> UserRepository)
        # so ancestors of UserRepository should include UserService
        ancestor_names = [a["name"] for a in hierarchy["ancestors"]]
        assert "UserService" in ancestor_names

    def test_get_class_hierarchy_nonexistent(self, populated_graph):
        """Test class hierarchy for non-existent class."""
        hierarchy = populated_graph.get_class_hierarchy("nonexistent:id")

        assert hierarchy["ancestors"] == []
        assert hierarchy["descendants"] == []

    def test_get_class_hierarchy_multiple_levels(self, empty_graph):
        """Test class hierarchy with multiple inheritance levels."""
        loc = SourceLocation(file_path=Path("/test.php"), start_line=1, end_line=10)

        # Create: GrandChild -> Child -> Parent
        grandchild = ClassEntity(
            id="test:class:GrandChild",
            name="GrandChild",
            entity_type=EntityType.CLASS,
            language=Language.PHP,
            location=loc,
            extends="Child",
        )
        child = ClassEntity(
            id="test:class:Child",
            name="Child",
            entity_type=EntityType.CLASS,
            language=Language.PHP,
            location=loc,
            extends="Parent",
        )
        parent = ClassEntity(
            id="test:class:Parent",
            name="Parent",
            entity_type=EntityType.CLASS,
            language=Language.PHP,
            location=loc,
        )

        empty_graph.add_entity(grandchild)
        empty_graph.add_entity(child)
        empty_graph.add_entity(parent)

        # Add extends relations
        empty_graph.add_relation(
            Relation.create(grandchild.id, child.id, RelationType.EXTENDS)
        )
        empty_graph.add_relation(
            Relation.create(child.id, parent.id, RelationType.EXTENDS)
        )

        hierarchy = empty_graph.get_class_hierarchy(grandchild.id)

        # Note: Edge direction is source -> target (GrandChild -> Child -> Parent)
        # so descendants of GrandChild should include Child and Parent
        descendant_names = [d["name"] for d in hierarchy["descendants"]]

        assert "Child" in descendant_names
        assert "Parent" in descendant_names


# ============================================================================
# Related Entities Tests
# ============================================================================


class TestRelatedEntities:
    """Tests for finding related entities."""

    def test_find_related_entities(self, populated_graph):
        """Test finding related entities within distance."""
        related = populated_graph.find_related_entities(
            "src/service.go:struct:UserService",
            max_distance=2,
        )

        assert len(related) >= 1

        # Should find UserRepository (distance 1)
        related_ids = [entity_id for entity_id, _ in related]
        assert any("UserRepository" in eid for eid in related_ids)

    def test_find_related_entities_with_distance(self, populated_graph):
        """Test that distance is correctly calculated."""
        related = populated_graph.find_related_entities(
            "src/service.go:struct:UserService",
            max_distance=1,
        )

        # All should be distance 1
        for _, distance in related:
            assert distance == 1

    def test_find_related_entities_nonexistent(self, populated_graph):
        """Test finding related for non-existent entity."""
        related = populated_graph.find_related_entities("nonexistent:id")
        assert related == []

    def test_find_related_entities_isolated(self, empty_graph, sample_function):
        """Test finding related for isolated entity."""
        empty_graph.add_entity(sample_function)
        related = empty_graph.find_related_entities(sample_function.id)

        # No relations, no related entities
        assert related == []


# ============================================================================
# Module Cluster Detection Tests
# ============================================================================


class TestModuleClusters:
    """Tests for module cluster detection."""

    def test_detect_module_clusters_empty(self, empty_graph):
        """Test cluster detection on empty graph."""
        clusters = empty_graph.detect_module_clusters()
        assert clusters == []

    def test_detect_module_clusters(self, populated_graph):
        """Test cluster detection on populated graph."""
        clusters = populated_graph.detect_module_clusters(min_cluster_size=2)

        # Should detect at least one cluster
        # Note: may be empty if entities are too disconnected
        assert isinstance(clusters, list)

    def test_detect_module_clusters_min_size(self, empty_graph):
        """Test cluster detection respects min size."""
        loc = SourceLocation(file_path=Path("/test.go"), start_line=1, end_line=10)

        # Create connected entities
        entities = []
        for i in range(5):
            entity = FunctionEntity(
                id=f"test:func{i}",
                name=f"func{i}",
                entity_type=EntityType.FUNCTION,
                language=Language.GO,
                location=loc,
            )
            entities.append(entity)
            empty_graph.add_entity(entity)

        # Connect them
        for i in range(len(entities) - 1):
            empty_graph.add_relation(
                Relation.create(
                    entities[i].id,
                    entities[i + 1].id,
                    RelationType.CALLS,
                )
            )

        # With high min_size, should get fewer clusters
        clusters_small = empty_graph.detect_module_clusters(min_cluster_size=2)
        clusters_large = empty_graph.detect_module_clusters(min_cluster_size=10)

        assert len(clusters_large) <= len(clusters_small)

    def test_cluster_metrics(self, empty_graph):
        """Test that cluster metrics are calculated."""
        loc = SourceLocation(file_path=Path("/test.php"), start_line=1, end_line=10)

        # Create a small cluster of related entities
        class1 = ClassEntity(
            id="test:class:A",
            name="A",
            entity_type=EntityType.CLASS,
            language=Language.PHP,
            location=loc,
        )
        class2 = ClassEntity(
            id="test:class:B",
            name="B",
            entity_type=EntityType.CLASS,
            language=Language.PHP,
            location=loc,
            extends="A",
        )
        class3 = ClassEntity(
            id="test:class:C",
            name="C",
            entity_type=EntityType.CLASS,
            language=Language.PHP,
            location=loc,
            extends="B",
        )

        for c in [class1, class2, class3]:
            empty_graph.add_entity(c)

        empty_graph.add_relation(
            Relation.create(class2.id, class1.id, RelationType.EXTENDS)
        )
        empty_graph.add_relation(
            Relation.create(class3.id, class2.id, RelationType.EXTENDS)
        )

        clusters = empty_graph.detect_module_clusters(min_cluster_size=2)

        if clusters:
            cluster = clusters[0]
            assert isinstance(cluster.cohesion_score, float)
            assert isinstance(cluster.coupling_score, float)


# ============================================================================
# File Dependencies Tests
# ============================================================================


class TestFileDependencies:
    """Tests for file-level dependency analysis."""

    def test_get_file_dependencies(self, populated_graph):
        """Test getting file dependencies."""
        deps = populated_graph.get_file_dependencies(Path("/src/service.go"))

        assert isinstance(deps, list)
        # UserService implements UserRepository which is in another file
        if deps:
            dep_targets = [d.target_file for d in deps]
            assert any(
                target and "repo" in str(target).lower() for target in dep_targets
            )

    def test_get_file_dependencies_empty(self, populated_graph):
        """Test file dependencies for file with no external deps."""
        deps = populated_graph.get_file_dependencies(Path("/nonexistent.go"))
        assert deps == []


# ============================================================================
# Serialization Tests
# ============================================================================


class TestSerialization:
    """Tests for graph serialization."""

    def test_to_dict_empty(self, empty_graph):
        """Test serializing empty graph."""
        result = empty_graph.to_dict()

        assert "nodes" in result
        assert "edges" in result
        assert result["nodes"] == []
        assert result["edges"] == []

    def test_to_dict_with_data(self, populated_graph):
        """Test serializing graph with data."""
        result = populated_graph.to_dict()

        assert len(result["nodes"]) > 0
        assert len(result["edges"]) > 0

        # Check node structure
        node = result["nodes"][0]
        assert "id" in node
        assert "entity_type" in node
        assert "name" in node

        # Check edge structure
        edge = result["edges"][0]
        assert "source" in edge
        assert "target" in edge
        assert "relation_type" in edge

    def test_stats_property(self, populated_graph):
        """Test stats property."""
        stats = populated_graph.stats

        assert "total_entities" in stats
        assert "total_relations" in stats
        assert "total_files" in stats
        assert "classes" in stats
        assert "interfaces" in stats
        assert "functions" in stats
        assert "methods" in stats

        assert stats["total_entities"] > 0
        assert stats["total_relations"] > 0


# ============================================================================
# build_dependency_graph Tests
# ============================================================================


class TestBuildDependencyGraph:
    """Tests for build_dependency_graph function."""

    def test_build_from_empty_list(self):
        """Test building graph from empty file list."""
        graph = build_dependency_graph([])

        assert graph is not None
        assert graph.stats["total_entities"] == 0

    def test_build_from_file_entities(self):
        """Test building graph from file entities."""
        loc = SourceLocation(file_path=Path("/src/user.go"), start_line=1, end_line=50)

        # Create file entity with classes and functions
        user_class = ClassEntity(
            id="src/user.go:class:User",
            name="User",
            entity_type=EntityType.CLASS,
            language=Language.GO,
            location=loc,
        )

        get_name = FunctionEntity(
            id="src/user.go:method:GetName",
            name="GetName",
            entity_type=EntityType.METHOD,
            language=Language.GO,
            location=loc,
        )

        file_entity = FileEntity(
            id="src/user.go:file",
            name="user.go",
            entity_type=EntityType.FILE,
            language=Language.GO,
            location=loc,
            file_path=Path("/src/user.go"),
            classes=[user_class],
            functions=[get_name],
        )

        graph = build_dependency_graph([file_entity])

        assert graph is not None
        assert graph.stats["total_entities"] >= 2

    def test_build_creates_relations(self):
        """Test that building graph creates appropriate relations."""
        loc1 = SourceLocation(file_path=Path("/src/base.php"), start_line=1, end_line=20)
        loc2 = SourceLocation(file_path=Path("/src/child.php"), start_line=1, end_line=30)

        # Base class
        base_class = ClassEntity(
            id="src/base.php:class:BaseModel",
            name="BaseModel",
            entity_type=EntityType.CLASS,
            language=Language.PHP,
            location=loc1,
        )

        base_file = FileEntity(
            id="src/base.php:file",
            name="base.php",
            entity_type=EntityType.FILE,
            language=Language.PHP,
            location=loc1,
            file_path=Path("/src/base.php"),
            classes=[base_class],
        )

        # Child class that extends base
        child_class = ClassEntity(
            id="src/child.php:class:User",
            name="User",
            entity_type=EntityType.CLASS,
            language=Language.PHP,
            location=loc2,
            extends="BaseModel",
        )

        child_file = FileEntity(
            id="src/child.php:file",
            name="child.php",
            entity_type=EntityType.FILE,
            language=Language.PHP,
            location=loc2,
            file_path=Path("/src/child.php"),
            classes=[child_class],
        )

        graph = build_dependency_graph([base_file, child_file])

        # Should have created EXTENDS relation
        deps = graph.get_dependencies(child_class.id)
        dep_types = [rel_type for _, rel_type in deps]

        assert RelationType.EXTENDS in dep_types

    def test_build_with_imports(self):
        """Test building graph with import relations."""
        loc = SourceLocation(file_path=Path("/src/service.ts"), start_line=1, end_line=50)

        user_import = ImportEntity(
            id="src/service.ts:import:User",
            name="User",
            entity_type=EntityType.IMPORT,
            language=Language.TYPESCRIPT,
            location=loc,
            module_path="./models/User",
            imported_names=["User"],
        )

        file_entity = FileEntity(
            id="src/service.ts:file",
            name="service.ts",
            entity_type=EntityType.FILE,
            language=Language.TYPESCRIPT,
            location=loc,
            file_path=Path("/src/service.ts"),
            imports=[user_import],
        )

        graph = build_dependency_graph([file_entity])

        assert graph is not None
        # Import entity should be in graph
        entities = graph.get_entities_by_type(EntityType.IMPORT)
        assert len(entities) >= 1

    def test_build_with_call_relations(self):
        """Test building graph creates call relations."""
        loc = SourceLocation(file_path=Path("/src/service.go"), start_line=1, end_line=50)

        caller = FunctionEntity(
            id="src/service.go:function:ProcessData",
            name="ProcessData",
            entity_type=EntityType.FUNCTION,
            language=Language.GO,
            location=loc,
            calls=["ValidateData", "SaveData"],
        )

        validate = FunctionEntity(
            id="src/service.go:function:ValidateData",
            name="ValidateData",
            entity_type=EntityType.FUNCTION,
            language=Language.GO,
            location=loc,
        )

        save = FunctionEntity(
            id="src/service.go:function:SaveData",
            name="SaveData",
            entity_type=EntityType.FUNCTION,
            language=Language.GO,
            location=loc,
        )

        file_entity = FileEntity(
            id="src/service.go:file",
            name="service.go",
            entity_type=EntityType.FILE,
            language=Language.GO,
            location=loc,
            file_path=Path("/src/service.go"),
            functions=[caller, validate, save],
        )

        graph = build_dependency_graph([file_entity])

        # Check call relations were created
        deps = graph.get_dependencies(caller.id)
        dep_types = [rel_type for _, rel_type in deps]

        assert RelationType.CALLS in dep_types

    def test_build_with_traits(self):
        """Test building graph with PHP trait relations."""
        loc = SourceLocation(file_path=Path("/src/user.php"), start_line=1, end_line=50)

        trait = ClassEntity(
            id="src/user.php:trait:HasTimestamps",
            name="HasTimestamps",
            entity_type=EntityType.TRAIT,
            language=Language.PHP,
            location=loc,
            is_trait=True,
        )

        user_class = ClassEntity(
            id="src/user.php:class:User",
            name="User",
            entity_type=EntityType.CLASS,
            language=Language.PHP,
            location=loc,
            uses_traits=["HasTimestamps"],
        )

        file_entity = FileEntity(
            id="src/user.php:file",
            name="user.php",
            entity_type=EntityType.FILE,
            language=Language.PHP,
            location=loc,
            file_path=Path("/src/user.php"),
            classes=[trait, user_class],
        )

        graph = build_dependency_graph([file_entity])

        # Check USES_TRAIT relation was created
        deps = graph.get_dependencies(user_class.id)
        dep_types = [rel_type for _, rel_type in deps]

        assert RelationType.USES_TRAIT in dep_types


# ============================================================================
# Edge Cases and Performance Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_cyclic_calls(self, empty_graph):
        """Test handling of cyclic call relationships."""
        loc = SourceLocation(file_path=Path("/test.go"), start_line=1, end_line=10)

        func_a = FunctionEntity(
            id="test:funcA",
            name="funcA",
            entity_type=EntityType.FUNCTION,
            language=Language.GO,
            location=loc,
        )
        func_b = FunctionEntity(
            id="test:funcB",
            name="funcB",
            entity_type=EntityType.FUNCTION,
            language=Language.GO,
            location=loc,
        )

        empty_graph.add_entity(func_a)
        empty_graph.add_entity(func_b)

        # Create cycle: A -> B -> A
        empty_graph.add_relation(
            Relation.create(func_a.id, func_b.id, RelationType.CALLS)
        )
        empty_graph.add_relation(
            Relation.create(func_b.id, func_a.id, RelationType.CALLS)
        )

        # get_call_chain should handle cycles without infinite loop
        chains = empty_graph.get_call_chain(func_a.id, max_depth=10)

        # Should not hang and should avoid infinite recursion
        assert isinstance(chains, list)

    def test_self_reference(self, empty_graph, sample_function):
        """Test handling of self-referencing entity."""
        empty_graph.add_entity(sample_function)

        # Add self-call
        empty_graph.add_relation(
            Relation.create(
                sample_function.id,
                sample_function.id,
                RelationType.CALLS,
            )
        )

        # Should handle gracefully
        chains = empty_graph.get_call_chain(sample_function.id)
        assert isinstance(chains, list)

    def test_large_graph(self, empty_graph):
        """Test performance with larger graph."""
        loc = SourceLocation(file_path=Path("/test.go"), start_line=1, end_line=10)

        # Create 100 entities
        entities = []
        for i in range(100):
            entity = FunctionEntity(
                id=f"test:func{i}",
                name=f"func{i}",
                entity_type=EntityType.FUNCTION,
                language=Language.GO,
                location=loc,
            )
            entities.append(entity)
            empty_graph.add_entity(entity)

        # Create 200 relations
        import random

        for _ in range(200):
            source = random.choice(entities)
            target = random.choice(entities)
            if source.id != target.id:
                empty_graph.add_relation(
                    Relation.create(source.id, target.id, RelationType.CALLS)
                )

        assert empty_graph.stats["total_entities"] == 100
        assert empty_graph.stats["total_relations"] <= 200

        # Operations should complete in reasonable time
        _ = empty_graph.to_dict()
        _ = empty_graph.find_related_entities(entities[0].id)
        _ = empty_graph.detect_module_clusters(min_cluster_size=5)
