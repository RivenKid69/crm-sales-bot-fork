"""Vector store for code embeddings using Qdrant.

Supports both local (file-based) and remote Qdrant instances.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
import json
import uuid

import numpy as np

from .embedder import CodeEmbedding


@dataclass
class StoreConfig:
    """Configuration for vector store."""

    # Qdrant connection
    mode: Literal["memory", "local", "remote"] = "local"
    local_path: Path | None = None
    remote_url: str = "http://localhost:6333"
    api_key: str | None = None

    # Collection settings
    collection_name: str = "code_embeddings"
    vector_size: int = 768  # Jina embeddings dimension
    distance_metric: Literal["cosine", "euclid", "dot"] = "cosine"

    # Search settings
    default_limit: int = 10
    search_accuracy: int = 100  # HNSW ef parameter


class EmbeddingStore:
    """Vector store for code embeddings.

    Uses Qdrant for efficient similarity search.
    Falls back to in-memory store if Qdrant is not available.
    """

    def __init__(self, config: StoreConfig | None = None):
        self.config = config or StoreConfig()
        self._client = None
        self._fallback_store: list[CodeEmbedding] = []
        self._using_fallback = False

    def _init_client(self):
        """Initialize Qdrant client."""
        if self._client is not None:
            return

        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import (
                Distance,
                VectorParams,
                PointStruct,
            )

            if self.config.mode == "memory":
                self._client = QdrantClient(":memory:")
            elif self.config.mode == "local":
                path = self.config.local_path or Path("./qdrant_data")
                path.mkdir(parents=True, exist_ok=True)
                self._client = QdrantClient(path=str(path))
            else:  # remote
                self._client = QdrantClient(
                    url=self.config.remote_url,
                    api_key=self.config.api_key,
                )

            # Ensure collection exists
            self._ensure_collection()
            self._using_fallback = False

        except ImportError:
            # Fallback to in-memory store
            self._using_fallback = True
        except Exception as e:
            # Connection error - fallback
            self._using_fallback = True

    def _ensure_collection(self):
        """Ensure the collection exists with correct settings."""
        from qdrant_client.models import Distance, VectorParams

        distance_map = {
            "cosine": Distance.COSINE,
            "euclid": Distance.EUCLID,
            "dot": Distance.DOT,
        }

        collections = self._client.get_collections().collections
        exists = any(c.name == self.config.collection_name for c in collections)

        if not exists:
            self._client.create_collection(
                collection_name=self.config.collection_name,
                vectors_config=VectorParams(
                    size=self.config.vector_size,
                    distance=distance_map[self.config.distance_metric],
                ),
            )

    @property
    def is_connected(self) -> bool:
        """Check if connected to Qdrant."""
        self._init_client()
        return not self._using_fallback

    def add(self, embedding: CodeEmbedding) -> str:
        """Add a single embedding to the store."""
        self._init_client()

        point_id = str(uuid.uuid4())

        if self._using_fallback:
            embedding.metadata["_point_id"] = point_id
            self._fallback_store.append(embedding)
            return point_id

        from qdrant_client.models import PointStruct

        payload = {
            "entity_id": embedding.entity_id,
            "text_hash": embedding.text_hash,
            "chunk_index": embedding.chunk_index,
            "total_chunks": embedding.total_chunks,
            **embedding.metadata,
        }

        self._client.upsert(
            collection_name=self.config.collection_name,
            points=[
                PointStruct(
                    id=point_id,
                    vector=embedding.vector.tolist(),
                    payload=payload,
                )
            ],
        )

        return point_id

    def add_many(self, embeddings: list[CodeEmbedding]) -> list[str]:
        """Add multiple embeddings in batch."""
        self._init_client()

        if not embeddings:
            return []

        point_ids = [str(uuid.uuid4()) for _ in embeddings]

        if self._using_fallback:
            for emb, pid in zip(embeddings, point_ids):
                emb.metadata["_point_id"] = pid
                self._fallback_store.append(emb)
            return point_ids

        from qdrant_client.models import PointStruct

        points = []
        for emb, pid in zip(embeddings, point_ids):
            payload = {
                "entity_id": emb.entity_id,
                "text_hash": emb.text_hash,
                "chunk_index": emb.chunk_index,
                "total_chunks": emb.total_chunks,
                **emb.metadata,
            }
            points.append(
                PointStruct(
                    id=pid,
                    vector=emb.vector.tolist(),
                    payload=payload,
                )
            )

        # Batch upsert
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            self._client.upsert(
                collection_name=self.config.collection_name,
                points=batch,
            )

        return point_ids

    def search(
        self,
        query_vector: np.ndarray,
        limit: int | None = None,
        filter_by: dict | None = None,
        score_threshold: float | None = None,
    ) -> list[tuple[CodeEmbedding, float]]:
        """Search for similar embeddings.

        Args:
            query_vector: Query embedding vector
            limit: Maximum results to return
            filter_by: Metadata filters (e.g., {"entity_type": "function"})
            score_threshold: Minimum similarity score

        Returns:
            List of (embedding, score) tuples
        """
        self._init_client()

        limit = limit or self.config.default_limit

        if self._using_fallback:
            return self._fallback_search(query_vector, limit, filter_by, score_threshold)

        from qdrant_client.models import Filter, FieldCondition, MatchValue

        # Build filter
        qdrant_filter = None
        if filter_by:
            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filter_by.items()
            ]
            qdrant_filter = Filter(must=conditions)

        results = self._client.search(
            collection_name=self.config.collection_name,
            query_vector=query_vector.tolist(),
            limit=limit,
            query_filter=qdrant_filter,
            score_threshold=score_threshold,
            search_params={"exact": False, "hnsw_ef": self.config.search_accuracy},
        )

        embeddings = []
        for result in results:
            payload = result.payload
            emb = CodeEmbedding(
                entity_id=payload["entity_id"],
                vector=np.array(result.vector) if result.vector else np.array([]),
                text_hash=payload.get("text_hash", ""),
                chunk_index=payload.get("chunk_index", 0),
                total_chunks=payload.get("total_chunks", 1),
                metadata={
                    k: v for k, v in payload.items()
                    if k not in ["entity_id", "text_hash", "chunk_index", "total_chunks"]
                },
            )
            embeddings.append((emb, result.score))

        return embeddings

    def _fallback_search(
        self,
        query_vector: np.ndarray,
        limit: int,
        filter_by: dict | None,
        score_threshold: float | None,
    ) -> list[tuple[CodeEmbedding, float]]:
        """In-memory fallback search."""
        results = []

        for emb in self._fallback_store:
            # Apply filter
            if filter_by:
                skip = False
                for k, v in filter_by.items():
                    if emb.metadata.get(k) != v:
                        skip = True
                        break
                if skip:
                    continue

            # Compute similarity (cosine)
            score = float(np.dot(query_vector, emb.vector))

            if score_threshold and score < score_threshold:
                continue

            results.append((emb, score))

        # Sort by score descending
        results.sort(key=lambda x: x[1], reverse=True)

        return results[:limit]

    def get_by_entity_id(self, entity_id: str) -> list[CodeEmbedding]:
        """Get all embeddings for an entity ID."""
        self._init_client()

        if self._using_fallback:
            return [e for e in self._fallback_store if e.entity_id == entity_id]

        from qdrant_client.models import Filter, FieldCondition, MatchValue

        results = self._client.scroll(
            collection_name=self.config.collection_name,
            scroll_filter=Filter(
                must=[FieldCondition(key="entity_id", match=MatchValue(value=entity_id))]
            ),
            with_vectors=True,
        )[0]

        embeddings = []
        for point in results:
            payload = point.payload
            emb = CodeEmbedding(
                entity_id=payload["entity_id"],
                vector=np.array(point.vector) if point.vector else np.array([]),
                text_hash=payload.get("text_hash", ""),
                chunk_index=payload.get("chunk_index", 0),
                total_chunks=payload.get("total_chunks", 1),
                metadata={
                    k: v for k, v in payload.items()
                    if k not in ["entity_id", "text_hash", "chunk_index", "total_chunks"]
                },
            )
            embeddings.append(emb)

        return embeddings

    def delete_by_entity_id(self, entity_id: str) -> int:
        """Delete all embeddings for an entity ID."""
        self._init_client()

        if self._using_fallback:
            before = len(self._fallback_store)
            self._fallback_store = [
                e for e in self._fallback_store if e.entity_id != entity_id
            ]
            return before - len(self._fallback_store)

        from qdrant_client.models import Filter, FieldCondition, MatchValue

        result = self._client.delete(
            collection_name=self.config.collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="entity_id", match=MatchValue(value=entity_id))]
            ),
        )

        return 1  # Qdrant doesn't return count

    def count(self) -> int:
        """Get total number of embeddings in store."""
        self._init_client()

        if self._using_fallback:
            return len(self._fallback_store)

        info = self._client.get_collection(self.config.collection_name)
        return info.points_count

    def clear(self):
        """Clear all embeddings from the store."""
        self._init_client()

        if self._using_fallback:
            self._fallback_store.clear()
            return

        self._client.delete_collection(self.config.collection_name)
        self._ensure_collection()

    def save_fallback(self, path: Path):
        """Save fallback store to file."""
        if not self._using_fallback:
            return

        data = [emb.to_dict() for emb in self._fallback_store]
        with open(path, "w") as f:
            json.dump(data, f)

    def load_fallback(self, path: Path):
        """Load fallback store from file."""
        if not path.exists():
            return

        with open(path) as f:
            data = json.load(f)

        self._using_fallback = True
        self._fallback_store = [CodeEmbedding.from_dict(d) for d in data]

    def get_stats(self) -> dict:
        """Get store statistics."""
        self._init_client()

        stats = {
            "using_qdrant": not self._using_fallback,
            "total_embeddings": self.count(),
        }

        if not self._using_fallback:
            info = self._client.get_collection(self.config.collection_name)
            stats.update({
                "collection_name": self.config.collection_name,
                "vector_size": info.config.params.vectors.size,
                "indexed_vectors": info.indexed_vectors_count,
            })
        else:
            stats["mode"] = "fallback_memory"

        return stats


class HybridSearch:
    """Combines vector similarity with keyword/metadata search.

    Useful for more precise code search that combines:
    - Semantic similarity (embeddings)
    - Exact keyword matches
    - Metadata filters (file type, entity type, etc.)
    """

    def __init__(self, store: EmbeddingStore):
        self.store = store

    def search(
        self,
        query_vector: np.ndarray,
        keywords: list[str] | None = None,
        entity_types: list[str] | None = None,
        file_patterns: list[str] | None = None,
        limit: int = 10,
        vector_weight: float = 0.7,
    ) -> list[tuple[CodeEmbedding, float]]:
        """Hybrid search combining vector and keyword matching.

        Args:
            query_vector: Semantic query vector
            keywords: Keywords that must appear in entity name or code
            entity_types: Filter by entity types ("function", "class", etc.)
            file_patterns: File path patterns to include
            limit: Maximum results
            vector_weight: Weight for vector similarity (0-1)

        Returns:
            List of (embedding, combined_score) tuples
        """
        # Build metadata filter
        filter_by = {}
        if entity_types and len(entity_types) == 1:
            filter_by["entity_type"] = entity_types[0]

        # Get vector search results (more than needed for reranking)
        vector_results = self.store.search(
            query_vector=query_vector,
            limit=limit * 3,
            filter_by=filter_by if filter_by else None,
        )

        # Apply additional filters and scoring
        scored_results = []
        for emb, vec_score in vector_results:
            # Entity type filter (for multiple types)
            if entity_types and len(entity_types) > 1:
                if emb.metadata.get("entity_type") not in entity_types:
                    continue

            # File pattern filter
            if file_patterns:
                file_path = emb.metadata.get("file_path", "")
                if not any(pattern in file_path for pattern in file_patterns):
                    continue

            # Keyword boost
            keyword_score = 0.0
            if keywords:
                name = emb.metadata.get("name", "").lower()
                for kw in keywords:
                    if kw.lower() in name:
                        keyword_score += 0.3  # Boost for keyword match

            # Combined score
            combined_score = (
                vector_weight * vec_score +
                (1 - vector_weight) * min(keyword_score, 1.0)
            )

            scored_results.append((emb, combined_score))

        # Sort by combined score
        scored_results.sort(key=lambda x: x[1], reverse=True)

        return scored_results[:limit]
