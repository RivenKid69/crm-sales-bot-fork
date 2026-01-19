"""Dependency graph builder for code analysis."""

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import networkx as nx

from ..models.entities import (
    ClassEntity,
    CodeEntity,
    EntityType,
    FileEntity,
    FunctionEntity,
)
from ..models.relations import (
    CallSite,
    DependencyInfo,
    ModuleCluster,
    Relation,
    RelationType,
)
from ...utils.logging import get_logger

logger = get_logger("dependency_graph")


@dataclass
class DependencyGraph:
    """Graph representing code dependencies and relationships.

    Uses NetworkX for graph operations with custom metadata.
    """

    # The main graph storing all relationships
    _graph: nx.DiGraph = field(default_factory=nx.DiGraph)

    # Indexes for fast lookup
    _entities_by_id: dict[str, CodeEntity] = field(default_factory=dict)
    _entities_by_file: dict[Path, list[str]] = field(default_factory=lambda: defaultdict(list))
    _entities_by_type: dict[EntityType, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )

    # Call graph (separate for performance)
    _call_graph: nx.DiGraph = field(default_factory=nx.DiGraph)

    # Class hierarchy
    _class_hierarchy: nx.DiGraph = field(default_factory=nx.DiGraph)

    def add_entity(self, entity: CodeEntity) -> None:
        """Add a code entity to the graph."""
        self._entities_by_id[entity.id] = entity
        self._entities_by_file[entity.location.file_path].append(entity.id)
        self._entities_by_type[entity.entity_type].append(entity.id)

        # Add as node in main graph
        self._graph.add_node(
            entity.id,
            entity_type=entity.entity_type.value,
            name=entity.name,
            language=entity.language.value,
            file=str(entity.location.file_path),
        )

    def add_relation(self, relation: Relation) -> None:
        """Add a relationship between entities."""
        self._graph.add_edge(
            relation.source_id,
            relation.target_id,
            relation_type=relation.relation_type.value,
            weight=relation.weight,
            **relation.metadata,
        )

        # Update specialized graphs
        if relation.relation_type == RelationType.CALLS:
            self._call_graph.add_edge(
                relation.source_id,
                relation.target_id,
                weight=relation.weight,
            )
        elif relation.relation_type in [RelationType.EXTENDS, RelationType.IMPLEMENTS]:
            self._class_hierarchy.add_edge(
                relation.source_id,
                relation.target_id,
                relation_type=relation.relation_type.value,
            )

    def get_entity(self, entity_id: str) -> CodeEntity | None:
        """Get an entity by ID."""
        return self._entities_by_id.get(entity_id)

    def get_entities_in_file(self, file_path: Path) -> list[CodeEntity]:
        """Get all entities in a file."""
        entity_ids = self._entities_by_file.get(file_path, [])
        return [self._entities_by_id[eid] for eid in entity_ids if eid in self._entities_by_id]

    def get_entities_by_type(self, entity_type: EntityType) -> list[CodeEntity]:
        """Get all entities of a specific type."""
        entity_ids = self._entities_by_type.get(entity_type, [])
        return [self._entities_by_id[eid] for eid in entity_ids if eid in self._entities_by_id]

    def get_dependencies(self, entity_id: str) -> list[tuple[str, RelationType]]:
        """Get all entities that this entity depends on."""
        deps: list[tuple[str, RelationType]] = []
        if entity_id in self._graph:
            for _, target, data in self._graph.out_edges(entity_id, data=True):
                rel_type = RelationType(data.get("relation_type", "depends_on"))
                deps.append((target, rel_type))
        return deps

    def get_dependents(self, entity_id: str) -> list[tuple[str, RelationType]]:
        """Get all entities that depend on this entity."""
        deps: list[tuple[str, RelationType]] = []
        if entity_id in self._graph:
            for source, _, data in self._graph.in_edges(entity_id, data=True):
                rel_type = RelationType(data.get("relation_type", "depends_on"))
                deps.append((source, rel_type))
        return deps

    def get_call_chain(
        self,
        start_entity_id: str,
        max_depth: int = 5,
    ) -> list[list[str]]:
        """Get call chains starting from an entity.

        Returns paths of function/method calls.
        """
        if start_entity_id not in self._call_graph:
            return []

        chains: list[list[str]] = []

        def dfs(current: str, path: list[str], depth: int) -> None:
            if depth > max_depth:
                return

            if len(path) > 1:
                chains.append(list(path))

            for _, callee in self._call_graph.out_edges(current):
                if callee not in path:  # Avoid cycles
                    path.append(callee)
                    dfs(callee, path, depth + 1)
                    path.pop()

        dfs(start_entity_id, [start_entity_id], 0)
        return chains

    def get_class_hierarchy(self, class_id: str) -> dict[str, Any]:
        """Get the class hierarchy for a class.

        Returns ancestors and descendants.
        """
        hierarchy: dict[str, Any] = {
            "ancestors": [],
            "descendants": [],
        }

        if class_id not in self._class_hierarchy:
            return hierarchy

        # Get ancestors (classes this class extends/implements)
        try:
            for ancestor in nx.ancestors(self._class_hierarchy, class_id):
                entity = self.get_entity(ancestor)
                if entity:
                    hierarchy["ancestors"].append(
                        {"id": ancestor, "name": entity.name}
                    )
        except nx.NetworkXError:
            pass

        # Get descendants (classes that extend/implement this class)
        try:
            for descendant in nx.descendants(self._class_hierarchy, class_id):
                entity = self.get_entity(descendant)
                if entity:
                    hierarchy["descendants"].append(
                        {"id": descendant, "name": entity.name}
                    )
        except nx.NetworkXError:
            pass

        return hierarchy

    def find_related_entities(
        self,
        entity_id: str,
        max_distance: int = 2,
    ) -> list[tuple[str, int]]:
        """Find entities related to a given entity within a distance.

        Uses BFS to find related entities.
        """
        if entity_id not in self._graph:
            return []

        related: list[tuple[str, int]] = []
        visited: set[str] = {entity_id}

        # BFS
        current_level = [entity_id]
        for distance in range(1, max_distance + 1):
            next_level: list[str] = []

            for node in current_level:
                # Get neighbors (both directions)
                neighbors = set(self._graph.successors(node)) | set(
                    self._graph.predecessors(node)
                )

                for neighbor in neighbors:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        next_level.append(neighbor)
                        related.append((neighbor, distance))

            current_level = next_level

        return related

    def detect_module_clusters(
        self,
        min_cluster_size: int = 3,
    ) -> list[ModuleCluster]:
        """Detect clusters of related files that form logical modules.

        Uses community detection algorithms.
        """
        # Create an undirected version for community detection
        undirected = self._graph.to_undirected()

        try:
            # Use Louvain community detection
            import community as community_louvain

            partition = community_louvain.best_partition(undirected)
        except ImportError:
            # Fallback to connected components
            components = list(nx.connected_components(undirected))
            partition = {}
            for i, component in enumerate(components):
                for node in component:
                    partition[node] = i

        # Group nodes by community
        communities: dict[int, list[str]] = defaultdict(list)
        for node, community_id in partition.items():
            communities[community_id].append(node)

        # Create ModuleCluster objects
        clusters: list[ModuleCluster] = []
        for community_id, nodes in communities.items():
            if len(nodes) < min_cluster_size:
                continue

            # Get unique files
            files: set[Path] = set()
            main_entities: list[str] = []

            for node_id in nodes:
                entity = self.get_entity(node_id)
                if entity:
                    files.add(entity.location.file_path)
                    # Classes and interfaces are main entities
                    if entity.entity_type in [EntityType.CLASS, EntityType.INTERFACE]:
                        main_entities.append(node_id)

            if files:
                # Calculate cohesion (internal edges / possible internal edges)
                subgraph = self._graph.subgraph(nodes)
                internal_edges = subgraph.number_of_edges()
                possible_edges = len(nodes) * (len(nodes) - 1)
                cohesion = internal_edges / possible_edges if possible_edges > 0 else 0

                # Calculate coupling (external edges / total edges)
                external_edges = 0
                for node in nodes:
                    for _, target in self._graph.out_edges(node):
                        if target not in nodes:
                            external_edges += 1

                total_edges = internal_edges + external_edges
                coupling = external_edges / total_edges if total_edges > 0 else 0

                cluster = ModuleCluster(
                    name=f"cluster_{community_id}",
                    files=list(files),
                    main_entities=main_entities[:5],  # Top 5
                    cohesion_score=cohesion,
                    coupling_score=coupling,
                )
                clusters.append(cluster)

        return sorted(clusters, key=lambda c: len(c.files), reverse=True)

    def get_file_dependencies(self, file_path: Path) -> list[DependencyInfo]:
        """Get all dependencies for a file."""
        dependencies: list[DependencyInfo] = []
        entity_ids = self._entities_by_file.get(file_path, [])

        for entity_id in entity_ids:
            for target_id, rel_type in self.get_dependencies(entity_id):
                target_entity = self.get_entity(target_id)
                if target_entity:
                    dep = DependencyInfo(
                        source_file=file_path,
                        target_file=target_entity.location.file_path,
                        source_entity=entity_id,
                        target_entity=target_id,
                        relation_type=rel_type,
                        is_external=False,
                    )
                    dependencies.append(dep)

        return dependencies

    def to_dict(self) -> dict[str, Any]:
        """Serialize the graph to a dictionary."""
        return {
            "nodes": [
                {
                    "id": node,
                    **self._graph.nodes[node],
                }
                for node in self._graph.nodes
            ],
            "edges": [
                {
                    "source": source,
                    "target": target,
                    **data,
                }
                for source, target, data in self._graph.edges(data=True)
            ],
        }

    @property
    def stats(self) -> dict[str, int]:
        """Get statistics about the graph."""
        return {
            "total_entities": len(self._entities_by_id),
            "total_relations": self._graph.number_of_edges(),
            "total_files": len(self._entities_by_file),
            "classes": len(self._entities_by_type.get(EntityType.CLASS, [])),
            "interfaces": len(self._entities_by_type.get(EntityType.INTERFACE, [])),
            "functions": len(self._entities_by_type.get(EntityType.FUNCTION, [])),
            "methods": len(self._entities_by_type.get(EntityType.METHOD, [])),
        }


def build_dependency_graph(file_entities: list[FileEntity]) -> DependencyGraph:
    """Build a dependency graph from a list of file entities.

    Args:
        file_entities: List of parsed file entities

    Returns:
        Populated dependency graph
    """
    graph = DependencyGraph()

    # First pass: add all entities
    for file_entity in file_entities:
        for entity in file_entity.all_entities:
            graph.add_entity(entity)

    # Second pass: build relationships
    for file_entity in file_entities:
        _build_file_relations(file_entity, graph)

    logger.info(f"Built dependency graph: {graph.stats}")
    return graph


def _build_file_relations(file_entity: FileEntity, graph: DependencyGraph) -> None:
    """Build relationships for entities in a file."""
    # Import relationships
    for import_entity in file_entity.imports:
        # Try to find the target entity
        for imported_name in import_entity.imported_names:
            # Search for matching entities
            for entity in graph.get_entities_by_type(EntityType.CLASS):
                if entity.name == imported_name:
                    relation = Relation.create(
                        file_entity.id,
                        entity.id,
                        RelationType.IMPORTS,
                    )
                    graph.add_relation(relation)
                    break

    # Class relationships
    for class_entity in file_entity.classes:
        if isinstance(class_entity, ClassEntity):
            # Extends
            if class_entity.extends:
                # Find the parent class
                for entity in graph.get_entities_by_type(EntityType.CLASS):
                    if entity.name == class_entity.extends:
                        relation = Relation.create(
                            class_entity.id,
                            entity.id,
                            RelationType.EXTENDS,
                        )
                        graph.add_relation(relation)
                        break

            # Implements
            for iface_name in class_entity.implements:
                for entity in graph.get_entities_by_type(EntityType.INTERFACE):
                    if entity.name == iface_name:
                        relation = Relation.create(
                            class_entity.id,
                            entity.id,
                            RelationType.IMPLEMENTS,
                        )
                        graph.add_relation(relation)
                        break

            # Uses traits
            for trait_name in class_entity.uses_traits:
                for entity in graph.get_entities_by_type(EntityType.TRAIT):
                    if entity.name == trait_name:
                        relation = Relation.create(
                            class_entity.id,
                            entity.id,
                            RelationType.USES_TRAIT,
                        )
                        graph.add_relation(relation)
                        break

            # Method calls
            for method in class_entity.methods:
                if isinstance(method, FunctionEntity):
                    _build_call_relations(method, graph)

    # Function calls
    for func_entity in file_entity.functions:
        if isinstance(func_entity, FunctionEntity):
            _build_call_relations(func_entity, graph)


def _build_call_relations(func_entity: FunctionEntity, graph: DependencyGraph) -> None:
    """Build call relationships for a function/method."""
    for call_name in func_entity.calls:
        # Try to find the called entity
        # This is a simplified version - in production, we'd need better resolution
        for entity in graph.get_entities_by_type(EntityType.FUNCTION):
            if entity.name == call_name:
                relation = Relation.create(
                    func_entity.id,
                    entity.id,
                    RelationType.CALLS,
                )
                graph.add_relation(relation)
                break

        for entity in graph.get_entities_by_type(EntityType.METHOD):
            if entity.name == call_name:
                relation = Relation.create(
                    func_entity.id,
                    entity.id,
                    RelationType.CALLS,
                )
                graph.add_relation(relation)
                break
