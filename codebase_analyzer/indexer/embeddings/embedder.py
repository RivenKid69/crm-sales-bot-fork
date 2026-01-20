"""Code embeddings generation using sentence-transformers.

Supports multiple embedding models optimized for code:
- jina-embeddings-v2-base-code (default, 768 dims)
- Voyage code embeddings (via API)
- All-MiniLM-L6-v2 (lightweight alternative)
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
import hashlib
import numpy as np

from ..models.entities import CodeEntity, FunctionEntity, ClassEntity


@dataclass
class EmbeddingConfig:
    """Configuration for code embeddings."""

    model_name: str = "jinaai/jina-embeddings-v2-base-code"
    device: str = "cpu"  # "cpu", "cuda", "mps"
    batch_size: int = 32
    max_seq_length: int = 8192  # Jina supports long context
    normalize_embeddings: bool = True
    show_progress: bool = True

    # Chunking settings for large code
    chunk_overlap: int = 100  # Token overlap between chunks
    max_chunk_tokens: int = 2048  # Max tokens per chunk


@dataclass
class CodeEmbedding:
    """Embedding for a code entity or chunk."""

    entity_id: str
    vector: np.ndarray
    text_hash: str
    chunk_index: int = 0  # For chunked entities
    total_chunks: int = 1
    metadata: dict = field(default_factory=dict)

    @property
    def dimension(self) -> int:
        return len(self.vector)

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "entity_id": self.entity_id,
            "vector": self.vector.tolist(),
            "text_hash": self.text_hash,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CodeEmbedding":
        """Create from dictionary."""
        return cls(
            entity_id=data["entity_id"],
            vector=np.array(data["vector"]),
            text_hash=data["text_hash"],
            chunk_index=data.get("chunk_index", 0),
            total_chunks=data.get("total_chunks", 1),
            metadata=data.get("metadata", {}),
        )


class CodeEmbedder:
    """Generate embeddings for code entities.

    Uses sentence-transformers for local embedding generation.
    Supports caching based on code hash to avoid re-embedding unchanged code.
    """

    def __init__(self, config: EmbeddingConfig | None = None):
        self.config = config or EmbeddingConfig()
        self._model = None
        self._cache: dict[str, CodeEmbedding] = {}

    @property
    def model(self):
        """Lazy load the embedding model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(
                    self.config.model_name,
                    device=self.config.device,
                )
                if hasattr(self._model, "max_seq_length"):
                    self._model.max_seq_length = self.config.max_seq_length
            except ImportError:
                raise ImportError(
                    "sentence-transformers is required. "
                    "Install with: pip install sentence-transformers"
                )
        return self._model

    @property
    def embedding_dimension(self) -> int:
        """Get embedding dimension for the model."""
        return self.model.get_sentence_embedding_dimension()

    def get_text_hash(self, text: str) -> str:
        """Compute hash of text for caching."""
        normalized = " ".join(text.split())  # Normalize whitespace
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def _prepare_code_text(self, entity: CodeEntity) -> str:
        """Prepare code text for embedding.

        Includes entity name, type, docstring, and source code.
        """
        parts = []

        # Entity type and name
        parts.append(f"{entity.entity_type.value}: {entity.name}")

        # Docstring if available
        if entity.docstring:
            parts.append(f"Description: {entity.docstring}")

        # Type-specific info
        if isinstance(entity, FunctionEntity):
            parts.append(f"Signature: {entity.signature}")
            if entity.calls:
                parts.append(f"Calls: {', '.join(entity.calls[:10])}")
        elif isinstance(entity, ClassEntity):
            if entity.extends:
                parts.append(f"Extends: {entity.extends}")
            if entity.implements:
                parts.append(f"Implements: {', '.join(entity.implements)}")
            method_names = [m.name for m in entity.methods]
            if method_names:
                parts.append(f"Methods: {', '.join(method_names[:15])}")

        # Source code
        if entity.source_code:
            parts.append(f"Code:\n{entity.source_code}")

        return "\n".join(parts)

    def embed_text(self, text: str, use_cache: bool = True) -> np.ndarray:
        """Embed a single text string."""
        text_hash = self.get_text_hash(text)

        # Check cache
        if use_cache and text_hash in self._cache:
            return self._cache[text_hash].vector

        # Generate embedding
        vector = self.model.encode(
            text,
            normalize_embeddings=self.config.normalize_embeddings,
            show_progress_bar=False,
        )

        return np.array(vector)

    def embed_texts(
        self,
        texts: list[str],
        show_progress: bool | None = None
    ) -> list[np.ndarray]:
        """Embed multiple texts in batches."""
        if show_progress is None:
            show_progress = self.config.show_progress

        vectors = self.model.encode(
            texts,
            batch_size=self.config.batch_size,
            normalize_embeddings=self.config.normalize_embeddings,
            show_progress_bar=show_progress,
        )

        return [np.array(v) for v in vectors]

    def embed_entity(
        self,
        entity: CodeEntity,
        use_cache: bool = True
    ) -> CodeEmbedding:
        """Embed a single code entity."""
        text = self._prepare_code_text(entity)
        text_hash = self.get_text_hash(text)

        # Check cache
        cache_key = f"{entity.id}:{text_hash}"
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]

        # Generate embedding
        vector = self.embed_text(text, use_cache=False)

        embedding = CodeEmbedding(
            entity_id=entity.id,
            vector=vector,
            text_hash=text_hash,
            metadata={
                "entity_type": entity.entity_type.value,
                "name": entity.name,
                "language": entity.language.value,
                "file_path": str(entity.location.file_path),
                "start_line": entity.location.start_line,
                "end_line": entity.location.end_line,
            },
        )

        # Cache result
        if use_cache:
            self._cache[cache_key] = embedding

        return embedding

    def embed_entities(
        self,
        entities: list[CodeEntity],
        use_cache: bool = True,
        show_progress: bool | None = None,
    ) -> list[CodeEmbedding]:
        """Embed multiple entities in batches.

        Uses batch processing for efficiency.
        """
        if not entities:
            return []

        # Prepare texts and check cache
        texts_to_embed = []
        entity_indices = []  # Track which entities need embedding
        results: list[CodeEmbedding | None] = [None] * len(entities)

        for i, entity in enumerate(entities):
            text = self._prepare_code_text(entity)
            text_hash = self.get_text_hash(text)
            cache_key = f"{entity.id}:{text_hash}"

            if use_cache and cache_key in self._cache:
                results[i] = self._cache[cache_key]
            else:
                texts_to_embed.append(text)
                entity_indices.append(i)

        # Batch embed new texts
        if texts_to_embed:
            vectors = self.embed_texts(texts_to_embed, show_progress=show_progress)

            for j, (text, vector) in enumerate(zip(texts_to_embed, vectors)):
                i = entity_indices[j]
                entity = entities[i]
                text_hash = self.get_text_hash(text)

                embedding = CodeEmbedding(
                    entity_id=entity.id,
                    vector=vector,
                    text_hash=text_hash,
                    metadata={
                        "entity_type": entity.entity_type.value,
                        "name": entity.name,
                        "language": entity.language.value,
                        "file_path": str(entity.location.file_path),
                        "start_line": entity.location.start_line,
                        "end_line": entity.location.end_line,
                    },
                )

                results[i] = embedding

                # Cache
                if use_cache:
                    cache_key = f"{entity.id}:{text_hash}"
                    self._cache[cache_key] = embedding

        return [r for r in results if r is not None]

    def embed_query(self, query: str) -> np.ndarray:
        """Embed a search query.

        For asymmetric search, query embedding may differ from document embedding.
        Most models handle this automatically.
        """
        return self.embed_text(query, use_cache=False)

    def similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        if self.config.normalize_embeddings:
            # Already normalized, just dot product
            return float(np.dot(vec1, vec2))
        else:
            # Need to normalize
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return float(np.dot(vec1, vec2) / (norm1 * norm2))

    def find_similar(
        self,
        query_vector: np.ndarray,
        embeddings: list[CodeEmbedding],
        top_k: int = 10,
        threshold: float = 0.0,
    ) -> list[tuple[CodeEmbedding, float]]:
        """Find most similar embeddings to a query vector.

        Returns list of (embedding, score) tuples sorted by similarity.
        """
        if not embeddings:
            return []

        # Compute all similarities
        scores = []
        for emb in embeddings:
            score = self.similarity(query_vector, emb.vector)
            if score >= threshold:
                scores.append((emb, score))

        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)

        return scores[:top_k]

    def clear_cache(self):
        """Clear the embedding cache."""
        self._cache.clear()

    def get_cache_stats(self) -> dict:
        """Get cache statistics."""
        return {
            "cached_embeddings": len(self._cache),
            "cache_size_mb": sum(
                e.vector.nbytes for e in self._cache.values()
            ) / (1024 * 1024),
        }
