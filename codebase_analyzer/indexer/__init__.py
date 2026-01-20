"""Indexer module for codebase parsing and graph building.

Provides:
- CodebaseIndexer: Main indexer orchestrator
- IndexResult: Result of indexing operation
- DependencyGraph: Graph structure for code dependencies
- Code entity models and relations
- Embeddings generation and storage
"""

from .indexer import CodebaseIndexer, IndexResult, create_indexer
from .graph.dependency_graph import DependencyGraph, build_dependency_graph
from .models.entities import (
    CodeEntity,
    ClassEntity,
    FunctionEntity,
    FileEntity,
    ComponentEntity,
    ImportEntity,
    EntityType,
    Language,
    SourceLocation,
)
from .models.relations import Relation, RelationType, CodebaseStats

__all__ = [
    # Main indexer
    "CodebaseIndexer",
    "IndexResult",
    "create_indexer",
    # Graph
    "DependencyGraph",
    "build_dependency_graph",
    # Entities
    "CodeEntity",
    "ClassEntity",
    "FunctionEntity",
    "FileEntity",
    "ComponentEntity",
    "ImportEntity",
    "EntityType",
    "Language",
    "SourceLocation",
    # Relations
    "Relation",
    "RelationType",
    "CodebaseStats",
]
