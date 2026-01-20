"""Embeddings module for code similarity search.

Provides:
- CodeEmbedder: Generate embeddings using sentence-transformers
- EmbeddingStore: Store and search embeddings via Qdrant
- HybridSearch: Combined vector + keyword search
"""

from .embedder import (
    CodeEmbedder,
    CodeEmbedding,
    EmbeddingConfig,
)
from .store import (
    EmbeddingStore,
    HybridSearch,
    StoreConfig,
)

__all__ = [
    "CodeEmbedder",
    "CodeEmbedding",
    "EmbeddingConfig",
    "EmbeddingStore",
    "HybridSearch",
    "StoreConfig",
]
