"""Tests for codebase_analyzer/indexer/models/relations.py - Relation data models."""

from pathlib import Path

import pytest

from codebase_analyzer.indexer.models.relations import (
    APIEndpoint,
    CallSite,
    CodebaseStats,
    DependencyInfo,
    ModuleCluster,
    Relation,
    RelationType,
    SQLQuery,
)

# ============================================================================
# RelationType Tests
# ============================================================================

class TestRelationType:
    """Tests for RelationType enum."""

    def test_inheritance_relation_types(self):
        """Test inheritance relation types are defined."""
        assert RelationType.EXTENDS.value == "extends"
        assert RelationType.IMPLEMENTS.value == "implements"
        assert RelationType.USES_TRAIT.value == "uses_trait"

    def test_dependency_relation_types(self):
        """Test dependency relation types are defined."""
        assert RelationType.IMPORTS.value == "imports"
        assert RelationType.REQUIRES.value == "requires"
        assert RelationType.DEPENDS_ON.value == "depends_on"

    def test_call_relation_types(self):
        """Test function call relation types are defined."""
        assert RelationType.CALLS.value == "calls"
        assert RelationType.CALLED_BY.value == "called_by"
        assert RelationType.OVERRIDES.value == "overrides"

    def test_data_relation_types(self):
        """Test data access relation types are defined."""
        assert RelationType.READS.value == "reads"
        assert RelationType.WRITES.value == "writes"
        assert RelationType.MODIFIES.value == "modifies"

    def test_type_relation_types(self):
        """Test type relation types are defined."""
        assert RelationType.RETURNS.value == "returns"
        assert RelationType.RECEIVES.value == "receives"
        assert RelationType.INSTANTIATES.value == "instantiates"

    def test_react_relation_types(self):
        """Test React-specific relation types are defined."""
        assert RelationType.RENDERS.value == "renders"
        assert RelationType.USES_HOOK.value == "uses_hook"
        assert RelationType.PROVIDES_CONTEXT.value == "provides_context"
        assert RelationType.CONSUMES_CONTEXT.value == "consumes_context"

    def test_database_relation_types(self):
        """Test database relation types are defined."""
        assert RelationType.QUERIES_TABLE.value == "queries_table"
        assert RelationType.INSERTS_TO.value == "inserts_to"
        assert RelationType.UPDATES_TABLE.value == "updates_table"
        assert RelationType.DELETES_FROM.value == "deletes_from"

    def test_all_relation_types_count(self):
        """Test total number of relation types."""
        # Ensure we have all expected relation types
        expected_count = 23  # Total defined relation types
        actual_count = len(RelationType)
        assert actual_count == expected_count

    def test_relation_type_is_string_enum(self):
        """Test RelationType is a string enum."""
        assert isinstance(RelationType.CALLS, str)
        assert RelationType.CALLS == "calls"

# ============================================================================
# Relation Tests
# ============================================================================

class TestRelation:
    """Tests for Relation dataclass."""

    def test_basic_creation(self):
        """Test creating a basic Relation."""
        relation = Relation(
            id="src/User.php:class:User--extends-->src/Model.php:class:Model",
            source_id="src/User.php:class:User",
            target_id="src/Model.php:class:Model",
            relation_type=RelationType.EXTENDS,
        )

        assert relation.source_id == "src/User.php:class:User"
        assert relation.target_id == "src/Model.php:class:Model"
        assert relation.relation_type == RelationType.EXTENDS
        assert relation.weight == 1.0
        assert relation.metadata == {}

    def test_relation_with_weight(self):
        """Test Relation with custom weight."""
        relation = Relation(
            id="test-relation",
            source_id="source",
            target_id="target",
            relation_type=RelationType.CALLS,
            weight=0.8,
        )

        assert relation.weight == 0.8

    def test_relation_with_metadata(self):
        """Test Relation with metadata."""
        relation = Relation(
            id="test-relation",
            source_id="source",
            target_id="target",
            relation_type=RelationType.CALLS,
            metadata={
                "line_number": 42,
                "is_conditional": True,
                "context": "inside loop",
            },
        )

        assert relation.metadata["line_number"] == 42
        assert relation.metadata["is_conditional"] is True

    def test_create_classmethod(self):
        """Test Relation.create factory method."""
        relation = Relation.create(
            source_id="src/User.php:method:save",
            target_id="src/Database.php:method:query",
            relation_type=RelationType.CALLS,
        )

        # Check auto-generated ID format
        assert "src/User.php:method:save" in relation.id
        assert "calls" in relation.id
        assert "src/Database.php:method:query" in relation.id
        assert "--" in relation.id
        assert "-->" in relation.id

        # Check fields
        assert relation.source_id == "src/User.php:method:save"
        assert relation.target_id == "src/Database.php:method:query"
        assert relation.relation_type == RelationType.CALLS

    def test_create_with_metadata(self):
        """Test Relation.create with metadata kwargs."""
        relation = Relation.create(
            source_id="source",
            target_id="target",
            relation_type=RelationType.IMPORTS,
            is_type_only=True,
            alias="Model",
        )

        assert relation.metadata["is_type_only"] is True
        assert relation.metadata["alias"] == "Model"

    def test_create_different_relation_types(self):
        """Test creating relations with different types."""
        extends = Relation.create("child", "parent", RelationType.EXTENDS)
        assert "extends" in extends.id

        implements = Relation.create("class", "interface", RelationType.IMPLEMENTS)
        assert "implements" in implements.id

        calls = Relation.create("caller", "callee", RelationType.CALLS)
        assert "calls" in calls.id

# ============================================================================
# DependencyInfo Tests
# ============================================================================

class TestDependencyInfo:
    """Tests for DependencyInfo dataclass."""

    def test_internal_dependency(self):
        """Test internal dependency (within codebase)."""
        dep = DependencyInfo(
            source_file=Path("/src/User.php"),
            target_file=Path("/src/Model.php"),
            source_entity="User",
            target_entity="Model",
            relation_type=RelationType.EXTENDS,
        )

        assert dep.source_file == Path("/src/User.php")
        assert dep.target_file == Path("/src/Model.php")
        assert dep.is_external is False
        assert dep.package_name is None

    def test_external_dependency(self):
        """Test external dependency (outside codebase)."""
        dep = DependencyInfo(
            source_file=Path("/src/main.go"),
            target_file=None,  # External has no file
            source_entity="main",
            target_entity="fmt.Println",
            relation_type=RelationType.CALLS,
            is_external=True,
            package_name="fmt",
        )

        assert dep.target_file is None
        assert dep.is_external is True
        assert dep.package_name == "fmt"

    def test_import_dependency(self):
        """Test import dependency."""
        dep = DependencyInfo(
            source_file=Path("/src/service.ts"),
            target_file=None,
            source_entity="UserService",
            target_entity="Injectable",
            relation_type=RelationType.IMPORTS,
            is_external=True,
            package_name="@nestjs/common",
        )

        assert dep.relation_type == RelationType.IMPORTS
        assert dep.package_name == "@nestjs/common"

# ============================================================================
# CallSite Tests
# ============================================================================

class TestCallSite:
    """Tests for CallSite dataclass."""

    def test_basic_call_site(self):
        """Test creating a basic CallSite."""
        call = CallSite(
            caller_id="src/User.php:method:save",
            callee_id="src/Database.php:method:query",
            line_number=42,
            column=8,
        )

        assert call.caller_id == "src/User.php:method:save"
        assert call.callee_id == "src/Database.php:method:query"
        assert call.line_number == 42
        assert call.column == 8
        assert call.arguments == []
        assert call.is_dynamic is False

    def test_call_site_with_arguments(self):
        """Test CallSite with tracked arguments."""
        call = CallSite(
            caller_id="caller",
            callee_id="callee",
            line_number=10,
            column=4,
            arguments=["$user", "$data", "'active'"],
        )

        assert len(call.arguments) == 3
        assert "$user" in call.arguments

    def test_dynamic_call_site(self):
        """Test dynamic/indirect call site."""
        call = CallSite(
            caller_id="caller",
            callee_id="unknown",
            line_number=20,
            column=12,
            is_dynamic=True,
        )

        assert call.is_dynamic is True

# ============================================================================
# SQLQuery Tests
# ============================================================================

class TestSQLQuery:
    """Tests for SQLQuery dataclass."""

    def test_select_query(self):
        """Test SELECT query extraction."""
        query = SQLQuery(
            query="SELECT id, name, email FROM users WHERE active = 1",
            query_type="SELECT",
            tables=["users"],
            columns=["id", "name", "email"],
            entity_id="src/User.php:method:getActiveUsers",
            line_number=45,
        )

        assert query.query_type == "SELECT"
        assert "users" in query.tables
        assert "name" in query.columns
        assert query.entity_id == "src/User.php:method:getActiveUsers"

    def test_insert_query(self):
        """Test INSERT query extraction."""
        query = SQLQuery(
            query="INSERT INTO users (name, email) VALUES (?, ?)",
            query_type="INSERT",
            tables=["users"],
            columns=["name", "email"],
        )

        assert query.query_type == "INSERT"
        assert len(query.columns) == 2

    def test_update_query(self):
        """Test UPDATE query extraction."""
        query = SQLQuery(
            query="UPDATE users SET status = 'active' WHERE id = ?",
            query_type="UPDATE",
            tables=["users"],
            columns=["status"],
        )

        assert query.query_type == "UPDATE"

    def test_delete_query(self):
        """Test DELETE query extraction."""
        query = SQLQuery(
            query="DELETE FROM sessions WHERE expired_at < NOW()",
            query_type="DELETE",
            tables=["sessions"],
        )

        assert query.query_type == "DELETE"
        assert query.columns == []

    def test_join_query(self):
        """Test query with JOINs."""
        query = SQLQuery(
            query="SELECT u.name, o.total FROM users u JOIN orders o ON u.id = o.user_id",
            query_type="SELECT",
            tables=["users", "orders"],
            columns=["name", "total"],
        )

        assert len(query.tables) == 2
        assert "users" in query.tables
        assert "orders" in query.tables

    def test_default_values(self):
        """Test default values."""
        query = SQLQuery(
            query="SELECT * FROM test",
            query_type="SELECT",
        )

        assert query.tables == []
        assert query.columns == []
        assert query.entity_id == ""
        assert query.line_number == 0

# ============================================================================
# APIEndpoint Tests
# ============================================================================

class TestAPIEndpoint:
    """Tests for APIEndpoint dataclass."""

    def test_get_endpoint(self):
        """Test GET endpoint."""
        endpoint = APIEndpoint(
            method="GET",
            path="/api/users",
            handler_id="src/UserController.php:method:index",
        )

        assert endpoint.method == "GET"
        assert endpoint.path == "/api/users"
        assert endpoint.handler_id == "src/UserController.php:method:index"
        assert endpoint.controller is None
        assert endpoint.middleware == []
        assert endpoint.auth_required is False

    def test_post_endpoint_with_auth(self):
        """Test POST endpoint with authentication."""
        endpoint = APIEndpoint(
            method="POST",
            path="/api/users",
            handler_id="UserController.create",
            controller="UserController",
            middleware=["auth", "validate"],
            auth_required=True,
        )

        assert endpoint.method == "POST"
        assert endpoint.auth_required is True
        assert "auth" in endpoint.middleware

    def test_endpoint_with_path_params(self):
        """Test endpoint with path parameters."""
        endpoint = APIEndpoint(
            method="GET",
            path="/api/users/:id",
            handler_id="UserController.show",
        )

        assert ":id" in endpoint.path

    def test_endpoint_with_multiple_middleware(self):
        """Test endpoint with multiple middleware."""
        endpoint = APIEndpoint(
            method="DELETE",
            path="/api/users/:id",
            handler_id="UserController.destroy",
            middleware=["auth", "admin", "rateLimit", "log"],
        )

        assert len(endpoint.middleware) == 4

# ============================================================================
# ModuleCluster Tests
# ============================================================================

class TestModuleCluster:
    """Tests for ModuleCluster dataclass."""

    def test_basic_cluster(self):
        """Test creating a basic ModuleCluster."""
        cluster = ModuleCluster(
            name="user-management",
        )

        assert cluster.name == "user-management"
        assert cluster.files == []
        assert cluster.main_entities == []
        assert cluster.description == ""
        assert cluster.cohesion_score == 0.0
        assert cluster.coupling_score == 0.0

    def test_cluster_with_files(self):
        """Test cluster with files."""
        cluster = ModuleCluster(
            name="auth",
            files=[
                Path("/src/auth/AuthController.php"),
                Path("/src/auth/AuthService.php"),
                Path("/src/auth/TokenManager.php"),
            ],
        )

        assert len(cluster.files) == 3
        assert Path("/src/auth/AuthController.php") in cluster.files

    def test_cluster_with_main_entities(self):
        """Test cluster with main entities."""
        cluster = ModuleCluster(
            name="user",
            main_entities=["User", "UserRepository", "UserService"],
        )

        assert "User" in cluster.main_entities
        assert len(cluster.main_entities) == 3

    def test_cluster_with_scores(self):
        """Test cluster with cohesion and coupling scores."""
        cluster = ModuleCluster(
            name="core",
            cohesion_score=0.85,
            coupling_score=0.25,
        )

        assert cluster.cohesion_score == 0.85
        assert cluster.coupling_score == 0.25

    def test_cluster_with_description(self):
        """Test cluster with description."""
        cluster = ModuleCluster(
            name="payments",
            description="Handles all payment processing including credit cards and PayPal",
        )

        assert "payment processing" in cluster.description

# ============================================================================
# CodebaseStats Tests
# ============================================================================

class TestCodebaseStats:
    """Tests for CodebaseStats dataclass."""

    def test_default_values(self):
        """Test CodebaseStats default values."""
        stats = CodebaseStats()

        assert stats.total_files == 0
        assert stats.total_lines == 0
        assert stats.total_classes == 0
        assert stats.total_functions == 0
        assert stats.total_methods == 0
        assert stats.total_interfaces == 0
        assert stats.total_traits == 0
        assert stats.total_components == 0
        assert stats.files_by_language == {}
        assert stats.lines_by_language == {}
        assert stats.total_imports == 0
        assert stats.total_relations == 0
        assert stats.external_dependencies == 0
        assert stats.total_sql_queries == 0
        assert stats.tables_accessed == set()
        assert stats.total_endpoints == 0
        assert stats.endpoints_by_method == {}

    def test_basic_stats(self):
        """Test CodebaseStats with basic values."""
        stats = CodebaseStats(
            total_files=100,
            total_lines=15000,
            total_classes=45,
            total_functions=120,
            total_methods=350,
        )

        assert stats.total_files == 100
        assert stats.total_lines == 15000
        assert stats.total_classes == 45

    def test_files_by_language(self):
        """Test files_by_language tracking."""
        stats = CodebaseStats(
            files_by_language={
                "php": 50,
                "go": 30,
                "typescript": 20,
            },
        )

        assert stats.files_by_language["php"] == 50
        assert stats.files_by_language["go"] == 30
        assert sum(stats.files_by_language.values()) == 100

    def test_lines_by_language(self):
        """Test lines_by_language tracking."""
        stats = CodebaseStats(
            lines_by_language={
                "php": 8000,
                "go": 4000,
                "typescript": 3000,
            },
        )

        assert stats.lines_by_language["php"] == 8000
        assert sum(stats.lines_by_language.values()) == 15000

    def test_tables_accessed(self):
        """Test tables_accessed as set."""
        stats = CodebaseStats(
            total_sql_queries=50,
            tables_accessed={"users", "orders", "products", "sessions"},
        )

        assert len(stats.tables_accessed) == 4
        assert "users" in stats.tables_accessed

    def test_endpoints_by_method(self):
        """Test endpoints_by_method tracking."""
        stats = CodebaseStats(
            total_endpoints=25,
            endpoints_by_method={
                "GET": 15,
                "POST": 5,
                "PUT": 3,
                "DELETE": 2,
            },
        )

        assert stats.endpoints_by_method["GET"] == 15
        assert sum(stats.endpoints_by_method.values()) == 25

    def test_to_dict_method(self):
        """Test to_dict serialization method."""
        stats = CodebaseStats(
            total_files=10,
            total_lines=1000,
            total_classes=5,
            total_functions=20,
            total_methods=30,
            total_interfaces=3,
            total_traits=2,
            total_components=4,
            files_by_language={"php": 6, "go": 4},
            lines_by_language={"php": 600, "go": 400},
            total_imports=50,
            total_relations=100,
            external_dependencies=15,
            total_sql_queries=8,
            tables_accessed={"users", "orders"},
            total_endpoints=12,
            endpoints_by_method={"GET": 8, "POST": 4},
        )

        result = stats.to_dict()

        # Check type
        assert isinstance(result, dict)

        # Check all fields are present
        assert result["total_files"] == 10
        assert result["total_lines"] == 1000
        assert result["total_classes"] == 5
        assert result["total_functions"] == 20
        assert result["total_methods"] == 30
        assert result["total_interfaces"] == 3
        assert result["total_traits"] == 2
        assert result["total_components"] == 4
        assert result["files_by_language"] == {"php": 6, "go": 4}
        assert result["lines_by_language"] == {"php": 600, "go": 400}
        assert result["total_imports"] == 50
        assert result["total_relations"] == 100
        assert result["external_dependencies"] == 15
        assert result["total_sql_queries"] == 8
        assert result["total_endpoints"] == 12
        assert result["endpoints_by_method"] == {"GET": 8, "POST": 4}

        # Check tables_accessed is converted to list
        assert isinstance(result["tables_accessed"], list)
        assert set(result["tables_accessed"]) == {"users", "orders"}

    def test_to_dict_empty_stats(self):
        """Test to_dict with empty/default stats."""
        stats = CodebaseStats()
        result = stats.to_dict()

        assert result["total_files"] == 0
        assert result["files_by_language"] == {}
        assert result["tables_accessed"] == []
        assert result["endpoints_by_method"] == {}

    def test_comprehensive_stats(self):
        """Test comprehensive codebase statistics."""
        stats = CodebaseStats(
            total_files=250,
            total_lines=45000,
            total_classes=85,
            total_functions=150,
            total_methods=420,
            total_interfaces=25,
            total_traits=10,
            total_components=35,
            files_by_language={
                "php": 100,
                "go": 80,
                "typescript": 50,
                "javascript": 20,
            },
            lines_by_language={
                "php": 20000,
                "go": 15000,
                "typescript": 8000,
                "javascript": 2000,
            },
            total_imports=800,
            total_relations=2500,
            external_dependencies=150,
            total_sql_queries=120,
            tables_accessed={
                "users",
                "orders",
                "products",
                "categories",
                "sessions",
                "logs",
            },
            total_endpoints=45,
            endpoints_by_method={
                "GET": 25,
                "POST": 10,
                "PUT": 5,
                "DELETE": 3,
                "PATCH": 2,
            },
        )

        # Verify consistency
        assert sum(stats.files_by_language.values()) == stats.total_files
        assert sum(stats.lines_by_language.values()) == stats.total_lines
        assert sum(stats.endpoints_by_method.values()) == stats.total_endpoints

        # Verify serialization
        result = stats.to_dict()
        assert len(result["tables_accessed"]) == 6

    def test_stats_modification(self):
        """Test that stats can be modified after creation."""
        stats = CodebaseStats()

        # Modify values
        stats.total_files = 10
        stats.total_lines = 1000
        stats.files_by_language["php"] = 10
        stats.tables_accessed.add("users")
        stats.tables_accessed.add("orders")

        assert stats.total_files == 10
        assert stats.files_by_language["php"] == 10
        assert len(stats.tables_accessed) == 2

# ============================================================================
# Integration Tests
# ============================================================================

class TestRelationIntegration:
    """Integration tests for relation models."""

    def test_build_relation_chain(self):
        """Test building a chain of relations."""
        # User extends Model
        extends_rel = Relation.create(
            "User",
            "Model",
            RelationType.EXTENDS,
        )

        # User implements UserInterface
        implements_rel = Relation.create(
            "User",
            "UserInterface",
            RelationType.IMPLEMENTS,
        )

        # User.save() calls Database.query()
        calls_rel = Relation.create(
            "User:save",
            "Database:query",
            RelationType.CALLS,
            line=42,
        )

        relations = [extends_rel, implements_rel, calls_rel]

        # Filter by type
        extends = [r for r in relations if r.relation_type == RelationType.EXTENDS]
        assert len(extends) == 1

        calls = [r for r in relations if r.relation_type == RelationType.CALLS]
        assert len(calls) == 1
        assert calls[0].metadata.get("line") == 42

    def test_dependency_tracking(self):
        """Test tracking dependencies across files."""
        deps = [
            DependencyInfo(
                source_file=Path("/src/User.php"),
                target_file=Path("/src/Model.php"),
                source_entity="User",
                target_entity="Model",
                relation_type=RelationType.EXTENDS,
            ),
            DependencyInfo(
                source_file=Path("/src/User.php"),
                target_file=None,
                source_entity="User",
                target_entity="Carbon",
                relation_type=RelationType.IMPORTS,
                is_external=True,
                package_name="nesbot/carbon",
            ),
        ]

        internal = [d for d in deps if not d.is_external]
        external = [d for d in deps if d.is_external]

        assert len(internal) == 1
        assert len(external) == 1
        assert external[0].package_name == "nesbot/carbon"

    def test_sql_analysis(self):
        """Test SQL query analysis."""
        queries = [
            SQLQuery("SELECT * FROM users", "SELECT", ["users"]),
            SQLQuery("SELECT * FROM orders", "SELECT", ["orders"]),
            SQLQuery("INSERT INTO users", "INSERT", ["users"]),
            SQLQuery("UPDATE users SET", "UPDATE", ["users"]),
            SQLQuery("DELETE FROM sessions", "DELETE", ["sessions"]),
        ]

        # Aggregate tables accessed
        all_tables = set()
        for q in queries:
            all_tables.update(q.tables)

        assert all_tables == {"users", "orders", "sessions"}

        # Count by type
        selects = [q for q in queries if q.query_type == "SELECT"]
        assert len(selects) == 2

    def test_endpoint_coverage(self):
        """Test API endpoint coverage analysis."""
        endpoints = [
            APIEndpoint("GET", "/api/users", "UserController.index"),
            APIEndpoint("POST", "/api/users", "UserController.store", auth_required=True),
            APIEndpoint("GET", "/api/users/:id", "UserController.show"),
            APIEndpoint("PUT", "/api/users/:id", "UserController.update", auth_required=True),
            APIEndpoint("DELETE", "/api/users/:id", "UserController.destroy", auth_required=True),
        ]

        # Count methods
        methods = {}
        for ep in endpoints:
            methods[ep.method] = methods.get(ep.method, 0) + 1

        assert methods == {"GET": 2, "POST": 1, "PUT": 1, "DELETE": 1}

        # Count authenticated endpoints
        auth_required = [ep for ep in endpoints if ep.auth_required]
        assert len(auth_required) == 3
