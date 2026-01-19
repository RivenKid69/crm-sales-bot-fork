"""Data models for code relationships and dependencies."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class RelationType(str, Enum):
    """Types of relationships between code entities."""

    # Inheritance & Implementation
    EXTENDS = "extends"
    IMPLEMENTS = "implements"
    USES_TRAIT = "uses_trait"

    # Dependencies
    IMPORTS = "imports"
    REQUIRES = "requires"  # PHP require/include
    DEPENDS_ON = "depends_on"

    # Function/Method relationships
    CALLS = "calls"
    CALLED_BY = "called_by"
    OVERRIDES = "overrides"

    # Data relationships
    READS = "reads"
    WRITES = "writes"
    MODIFIES = "modifies"

    # Type relationships
    RETURNS = "returns"
    RECEIVES = "receives"  # parameter type
    INSTANTIATES = "instantiates"

    # React specific
    RENDERS = "renders"  # Component renders another
    USES_HOOK = "uses_hook"
    PROVIDES_CONTEXT = "provides_context"
    CONSUMES_CONTEXT = "consumes_context"

    # Database
    QUERIES_TABLE = "queries_table"
    INSERTS_TO = "inserts_to"
    UPDATES_TABLE = "updates_table"
    DELETES_FROM = "deletes_from"


@dataclass
class Relation:
    """Represents a relationship between two code entities."""

    id: str
    source_id: str  # Entity ID of the source
    target_id: str  # Entity ID of the target
    relation_type: RelationType
    weight: float = 1.0  # Relationship strength (for ranking)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        source_id: str,
        target_id: str,
        relation_type: RelationType,
        **metadata: Any,
    ) -> "Relation":
        """Create a new relation with auto-generated ID."""
        rel_id = f"{source_id}--{relation_type.value}-->{target_id}"
        return cls(
            id=rel_id,
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            metadata=metadata,
        )


@dataclass
class DependencyInfo:
    """Information about a dependency."""

    source_file: Path
    target_file: Path | None  # None if external
    source_entity: str
    target_entity: str
    relation_type: RelationType
    is_external: bool = False  # True if dependency is outside codebase
    package_name: str | None = None  # For external packages


@dataclass
class CallSite:
    """Information about a function/method call site."""

    caller_id: str
    callee_id: str
    line_number: int
    column: int
    arguments: list[str] = field(default_factory=list)
    is_dynamic: bool = False  # True if call target is dynamic


@dataclass
class SQLQuery:
    """Extracted SQL query information."""

    query: str
    query_type: str  # SELECT, INSERT, UPDATE, DELETE, etc.
    tables: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    entity_id: str = ""  # Entity where query was found
    line_number: int = 0


@dataclass
class APIEndpoint:
    """Extracted API endpoint information."""

    method: str  # GET, POST, etc.
    path: str
    handler_id: str  # Entity ID of the handler
    controller: str | None = None
    middleware: list[str] = field(default_factory=list)
    auth_required: bool = False


@dataclass
class ModuleCluster:
    """A cluster of related files forming a logical module."""

    name: str
    files: list[Path] = field(default_factory=list)
    main_entities: list[str] = field(default_factory=list)  # Key classes/interfaces
    description: str = ""
    cohesion_score: float = 0.0  # How tightly coupled are internal components
    coupling_score: float = 0.0  # How coupled with external modules


@dataclass
class CodebaseStats:
    """Statistics about the indexed codebase."""

    total_files: int = 0
    total_lines: int = 0
    total_classes: int = 0
    total_functions: int = 0
    total_methods: int = 0
    total_interfaces: int = 0
    total_traits: int = 0
    total_components: int = 0  # React

    # By language
    files_by_language: dict[str, int] = field(default_factory=dict)
    lines_by_language: dict[str, int] = field(default_factory=dict)

    # Dependencies
    total_imports: int = 0
    total_relations: int = 0
    external_dependencies: int = 0

    # SQL
    total_sql_queries: int = 0
    tables_accessed: set[str] = field(default_factory=set)

    # API
    total_endpoints: int = 0
    endpoints_by_method: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total_files": self.total_files,
            "total_lines": self.total_lines,
            "total_classes": self.total_classes,
            "total_functions": self.total_functions,
            "total_methods": self.total_methods,
            "total_interfaces": self.total_interfaces,
            "total_traits": self.total_traits,
            "total_components": self.total_components,
            "files_by_language": self.files_by_language,
            "lines_by_language": self.lines_by_language,
            "total_imports": self.total_imports,
            "total_relations": self.total_relations,
            "external_dependencies": self.external_dependencies,
            "total_sql_queries": self.total_sql_queries,
            "tables_accessed": list(self.tables_accessed),
            "total_endpoints": self.total_endpoints,
            "endpoints_by_method": self.endpoints_by_method,
        }
