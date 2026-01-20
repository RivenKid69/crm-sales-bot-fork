"""Tests for embeddings module (embedder and store)."""

import pytest
import numpy as np
from pathlib import Path
from unittest.mock import MagicMock, patch

from codebase_analyzer.indexer.embeddings.embedder import (
    CodeEmbedder,
    CodeEmbedding,
    EmbeddingConfig,
)
from codebase_analyzer.indexer.embeddings.store import (
    EmbeddingStore,
    StoreConfig,
    HybridSearch,
)
from codebase_analyzer.indexer.models.entities import (
    FunctionEntity,
    ClassEntity,
    EntityType,
    SourceLocation,
    Language,
    Parameter,
)


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
        docstring="Calculate total price with optional discount.",
        parameters=[
            Parameter(name="items", type_hint="list[Item]"),
            Parameter(name="discount", type_hint="float", default_value="0.0"),
        ],
        calls=["sum"],
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
    def __init__(self, db: Database):
        self.db = db

    def create_order(self, user_id: str, items: list) -> Order:
        pass
""",
        docstring="Manages order lifecycle.",
        extends="BaseService",
        implements=["IOrderService"],
    )


@pytest.fixture
def mock_model():
    """Mock sentence transformer model."""
    model = MagicMock()
    model.get_sentence_embedding_dimension.return_value = 768
    model.encode.return_value = np.random.randn(768).astype(np.float32)
    return model


@pytest.fixture
def mock_embedder(mock_model):
    """Create embedder with mocked model."""
    embedder = CodeEmbedder()
    embedder._model = mock_model
    return embedder


# ============================================================================
# Tests: EmbeddingConfig
# ============================================================================

class TestEmbeddingConfig:
    """Tests for EmbeddingConfig dataclass."""

    def test_default_config(self):
        """Should create config with defaults."""
        config = EmbeddingConfig()

        assert config.model_name == "jinaai/jina-embeddings-v2-base-code"
        assert config.device == "cpu"
        assert config.batch_size == 32
        assert config.max_seq_length == 8192
        assert config.normalize_embeddings is True

    def test_custom_config(self):
        """Should create config with custom values."""
        config = EmbeddingConfig(
            model_name="custom-model",
            device="cuda",
            batch_size=64,
        )

        assert config.model_name == "custom-model"
        assert config.device == "cuda"
        assert config.batch_size == 64


# ============================================================================
# Tests: CodeEmbedding
# ============================================================================

class TestCodeEmbedding:
    """Tests for CodeEmbedding dataclass."""

    def test_create_embedding(self):
        """Should create an embedding."""
        vector = np.random.randn(768).astype(np.float32)
        emb = CodeEmbedding(
            entity_id="test::func",
            vector=vector,
            text_hash="abc123",
        )

        assert emb.entity_id == "test::func"
        assert emb.dimension == 768
        assert emb.chunk_index == 0
        assert emb.total_chunks == 1

    def test_serialization_roundtrip(self):
        """Should serialize and deserialize correctly."""
        vector = np.random.randn(768).astype(np.float32)
        original = CodeEmbedding(
            entity_id="test::func",
            vector=vector,
            text_hash="abc123",
            chunk_index=1,
            total_chunks=3,
            metadata={"name": "func", "type": "function"},
        )

        data = original.to_dict()
        restored = CodeEmbedding.from_dict(data)

        assert restored.entity_id == original.entity_id
        assert restored.text_hash == original.text_hash
        assert restored.chunk_index == original.chunk_index
        assert np.allclose(restored.vector, original.vector)


# ============================================================================
# Tests: CodeEmbedder
# ============================================================================

class TestCodeEmbedder:
    """Tests for CodeEmbedder class."""

    def test_init_with_defaults(self):
        """Should initialize with default config."""
        embedder = CodeEmbedder()
        assert embedder.config.model_name == "jinaai/jina-embeddings-v2-base-code"
        assert embedder._model is None  # Lazy loaded

    def test_get_text_hash(self, mock_embedder):
        """Should compute consistent hash."""
        hash1 = mock_embedder.get_text_hash("def foo(): pass")
        hash2 = mock_embedder.get_text_hash("def foo(): pass")

        assert hash1 == hash2
        assert len(hash1) == 16

    def test_get_text_hash_ignores_whitespace(self, mock_embedder):
        """Hash should normalize whitespace."""
        hash1 = mock_embedder.get_text_hash("def foo():  return   1")
        hash2 = mock_embedder.get_text_hash("def foo(): return 1")

        assert hash1 == hash2

    def test_prepare_code_text_function(self, mock_embedder, sample_function):
        """Should prepare function text with signature and calls."""
        text = mock_embedder._prepare_code_text(sample_function)

        assert "function: calculate_total" in text.lower()
        assert "Signature:" in text
        assert "calculate_total" in text
        assert "Calls:" in text
        assert "sum" in text

    def test_prepare_code_text_class(self, mock_embedder, sample_class):
        """Should prepare class text with inheritance."""
        text = mock_embedder._prepare_code_text(sample_class)

        assert "class: orderservice" in text.lower()
        assert "Extends: BaseService" in text
        assert "Implements: IOrderService" in text

    def test_embed_text(self, mock_embedder, mock_model):
        """Should embed a text string."""
        mock_model.encode.return_value = np.ones(768)

        vector = mock_embedder.embed_text("test code")

        mock_model.encode.assert_called_once()
        assert len(vector) == 768

    def test_embed_texts_batch(self, mock_embedder, mock_model):
        """Should embed multiple texts in batch."""
        mock_model.encode.return_value = [np.ones(768), np.ones(768) * 2]

        texts = ["code1", "code2"]
        vectors = mock_embedder.embed_texts(texts, show_progress=False)

        mock_model.encode.assert_called_once()
        assert len(vectors) == 2

    def test_embed_entity(self, mock_embedder, mock_model, sample_function):
        """Should embed a code entity."""
        mock_model.encode.return_value = np.ones(768)

        embedding = mock_embedder.embed_entity(sample_function)

        assert embedding.entity_id == sample_function.id
        assert len(embedding.vector) == 768
        assert embedding.metadata["entity_type"] == "function"
        assert embedding.metadata["name"] == "calculate_total"

    def test_embed_entity_caching(self, mock_embedder, mock_model, sample_function):
        """Should cache embedding results."""
        mock_model.encode.return_value = np.ones(768)

        emb1 = mock_embedder.embed_entity(sample_function)
        emb2 = mock_embedder.embed_entity(sample_function)

        # Should only call encode once (cached)
        assert mock_model.encode.call_count == 1
        assert emb1.entity_id == emb2.entity_id

    def test_embed_entities_batch(self, mock_embedder, mock_model, sample_function, sample_class):
        """Should embed multiple entities in batch."""
        mock_model.encode.return_value = [np.ones(768), np.ones(768) * 2]

        entities = [sample_function, sample_class]
        embeddings = mock_embedder.embed_entities(entities, show_progress=False)

        assert len(embeddings) == 2
        assert embeddings[0].entity_id == sample_function.id
        assert embeddings[1].entity_id == sample_class.id

    def test_similarity_normalized(self, mock_embedder):
        """Should compute cosine similarity for normalized vectors."""
        vec1 = np.array([1, 0, 0], dtype=np.float32)
        vec2 = np.array([1, 0, 0], dtype=np.float32)

        sim = mock_embedder.similarity(vec1, vec2)
        assert sim == pytest.approx(1.0)

        vec3 = np.array([0, 1, 0], dtype=np.float32)
        sim2 = mock_embedder.similarity(vec1, vec3)
        assert sim2 == pytest.approx(0.0)

    def test_find_similar(self, mock_embedder):
        """Should find most similar embeddings."""
        query = np.array([1, 0, 0], dtype=np.float32)
        embeddings = [
            CodeEmbedding("e1", np.array([1, 0, 0]), "h1"),  # Same
            CodeEmbedding("e2", np.array([0, 1, 0]), "h2"),  # Orthogonal
            CodeEmbedding("e3", np.array([0.9, 0.1, 0]), "h3"),  # Similar
        ]

        results = mock_embedder.find_similar(query, embeddings, top_k=2)

        assert len(results) == 2
        assert results[0][0].entity_id == "e1"  # Most similar
        assert results[1][0].entity_id == "e3"

    def test_clear_cache(self, mock_embedder, mock_model, sample_function):
        """Should clear embedding cache."""
        mock_model.encode.return_value = np.ones(768)

        mock_embedder.embed_entity(sample_function)
        assert len(mock_embedder._cache) == 1

        mock_embedder.clear_cache()
        assert len(mock_embedder._cache) == 0

    def test_get_cache_stats(self, mock_embedder, mock_model, sample_function):
        """Should return cache statistics."""
        mock_model.encode.return_value = np.ones(768, dtype=np.float32)

        mock_embedder.embed_entity(sample_function)

        stats = mock_embedder.get_cache_stats()
        assert stats["cached_embeddings"] == 1
        assert stats["cache_size_mb"] > 0


# ============================================================================
# Tests: StoreConfig
# ============================================================================

class TestStoreConfig:
    """Tests for StoreConfig dataclass."""

    def test_default_config(self):
        """Should create config with defaults."""
        config = StoreConfig()

        assert config.mode == "local"
        assert config.collection_name == "code_embeddings"
        assert config.vector_size == 768
        assert config.distance_metric == "cosine"

    def test_memory_mode(self):
        """Should support memory mode."""
        config = StoreConfig(mode="memory")
        assert config.mode == "memory"


# ============================================================================
# Tests: EmbeddingStore (fallback mode)
# ============================================================================

class TestEmbeddingStoreFallback:
    """Tests for EmbeddingStore in fallback mode (no Qdrant)."""

    @pytest.fixture
    def fallback_store(self):
        """Create store that will use fallback."""
        with patch.dict("sys.modules", {"qdrant_client": None}):
            store = EmbeddingStore(StoreConfig(mode="memory"))
            store._using_fallback = True
            store._fallback_store = []
            return store

    def test_add_embedding(self, fallback_store):
        """Should add embedding to fallback store."""
        emb = CodeEmbedding(
            entity_id="test::func",
            vector=np.ones(768),
            text_hash="abc123",
        )

        point_id = fallback_store.add(emb)

        assert point_id is not None
        assert len(fallback_store._fallback_store) == 1

    def test_add_many(self, fallback_store):
        """Should add multiple embeddings."""
        embeddings = [
            CodeEmbedding("e1", np.ones(768), "h1"),
            CodeEmbedding("e2", np.ones(768) * 2, "h2"),
        ]

        point_ids = fallback_store.add_many(embeddings)

        assert len(point_ids) == 2
        assert fallback_store.count() == 2

    def test_search(self, fallback_store):
        """Should search in fallback store."""
        embeddings = [
            CodeEmbedding("e1", np.array([1, 0, 0] + [0]*765), "h1"),
            CodeEmbedding("e2", np.array([0, 1, 0] + [0]*765), "h2"),
        ]
        fallback_store.add_many(embeddings)

        query = np.array([1, 0, 0] + [0]*765)
        results = fallback_store.search(query, limit=10)

        assert len(results) == 2
        assert results[0][0].entity_id == "e1"  # Most similar

    def test_search_with_filter(self, fallback_store):
        """Should filter search results."""
        emb1 = CodeEmbedding("e1", np.ones(768), "h1", metadata={"entity_type": "function"})
        emb2 = CodeEmbedding("e2", np.ones(768), "h2", metadata={"entity_type": "class"})
        fallback_store.add_many([emb1, emb2])

        query = np.ones(768)
        results = fallback_store.search(query, filter_by={"entity_type": "function"})

        assert len(results) == 1
        assert results[0][0].entity_id == "e1"

    def test_get_by_entity_id(self, fallback_store):
        """Should get embeddings by entity ID."""
        emb1 = CodeEmbedding("e1", np.ones(768), "h1")
        emb2 = CodeEmbedding("e2", np.ones(768), "h2")
        fallback_store.add_many([emb1, emb2])

        results = fallback_store.get_by_entity_id("e1")

        assert len(results) == 1
        assert results[0].entity_id == "e1"

    def test_delete_by_entity_id(self, fallback_store):
        """Should delete embeddings by entity ID."""
        emb1 = CodeEmbedding("e1", np.ones(768), "h1")
        emb2 = CodeEmbedding("e2", np.ones(768), "h2")
        fallback_store.add_many([emb1, emb2])

        deleted = fallback_store.delete_by_entity_id("e1")

        assert deleted == 1
        assert fallback_store.count() == 1

    def test_clear(self, fallback_store):
        """Should clear all embeddings."""
        emb = CodeEmbedding("e1", np.ones(768), "h1")
        fallback_store.add(emb)
        assert fallback_store.count() == 1

        fallback_store.clear()
        assert fallback_store.count() == 0

    def test_save_and_load_fallback(self, fallback_store, tmp_path):
        """Should save and load fallback store."""
        emb = CodeEmbedding("e1", np.ones(768), "h1", metadata={"name": "func"})
        fallback_store.add(emb)

        save_path = tmp_path / "embeddings.json"
        fallback_store.save_fallback(save_path)

        # Load into new store
        new_store = EmbeddingStore()
        new_store._using_fallback = True
        new_store._fallback_store = []
        new_store.load_fallback(save_path)

        assert new_store.count() == 1
        loaded = new_store.get_by_entity_id("e1")[0]
        assert loaded.metadata["name"] == "func"


# ============================================================================
# Tests: HybridSearch
# ============================================================================

class TestHybridSearch:
    """Tests for HybridSearch class."""

    @pytest.fixture
    def store_with_data(self):
        """Create store with test data."""
        store = EmbeddingStore()
        store._using_fallback = True
        store._fallback_store = []

        embeddings = [
            CodeEmbedding(
                "func1",
                np.array([1, 0, 0] + [0]*765),
                "h1",
                metadata={"entity_type": "function", "name": "calculate_total", "file_path": "src/calc.py"},
            ),
            CodeEmbedding(
                "func2",
                np.array([0.9, 0.1, 0] + [0]*765),
                "h2",
                metadata={"entity_type": "function", "name": "get_price", "file_path": "src/price.py"},
            ),
            CodeEmbedding(
                "class1",
                np.array([0, 1, 0] + [0]*765),
                "h3",
                metadata={"entity_type": "class", "name": "OrderService", "file_path": "src/order.py"},
            ),
        ]
        store.add_many(embeddings)
        return store

    def test_search_basic(self, store_with_data):
        """Should perform basic hybrid search."""
        search = HybridSearch(store_with_data)

        query = np.array([1, 0, 0] + [0]*765)
        results = search.search(query, limit=10)

        assert len(results) >= 1
        # func1 should be top result (exact match)
        assert results[0][0].entity_id == "func1"

    def test_search_with_keyword_boost(self, store_with_data):
        """Should boost results matching keywords."""
        search = HybridSearch(store_with_data)

        query = np.array([0.5, 0.5, 0] + [0]*765)  # Between func1 and class1
        results = search.search(
            query,
            keywords=["calculate"],
            limit=10,
            vector_weight=0.5,
        )

        # calculate_total should be boosted
        func1_rank = next(
            (i for i, (e, _) in enumerate(results) if e.entity_id == "func1"),
            None
        )
        assert func1_rank is not None

    def test_search_with_entity_type_filter(self, store_with_data):
        """Should filter by entity type."""
        search = HybridSearch(store_with_data)

        query = np.array([0.5, 0.5, 0] + [0]*765)
        results = search.search(
            query,
            entity_types=["function"],
            limit=10,
        )

        # Should only have functions
        for emb, _ in results:
            assert emb.metadata["entity_type"] == "function"

    def test_search_with_file_pattern(self, store_with_data):
        """Should filter by file pattern."""
        search = HybridSearch(store_with_data)

        query = np.array([0.5, 0.5, 0] + [0]*765)
        results = search.search(
            query,
            file_patterns=["calc.py"],
            limit=10,
        )

        assert len(results) == 1
        assert "calc.py" in results[0][0].metadata["file_path"]


# ============================================================================
# Tests: Integration
# ============================================================================

class TestEmbeddingsIntegration:
    """Integration tests for embedder + store."""

    def test_embedder_to_store_roundtrip(self, mock_embedder, mock_model, sample_function):
        """Should embed entities and store/retrieve them."""
        mock_model.encode.return_value = np.random.randn(768).astype(np.float32)

        # Embed entity
        embedding = mock_embedder.embed_entity(sample_function)

        # Store embedding
        store = EmbeddingStore()
        store._using_fallback = True
        store._fallback_store = []
        store.add(embedding)

        # Search
        query = mock_embedder.embed_query("calculate total price")
        results = store.search(query, limit=1)

        assert len(results) == 1
        assert results[0][0].entity_id == sample_function.id
