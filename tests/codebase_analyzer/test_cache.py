"""Tests for analysis cache module."""

import json
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from codebase_analyzer.analyzer.cache import AnalysisCache, CacheEntry
from codebase_analyzer.analyzer.models import EntitySummary
from codebase_analyzer.indexer.models.entities import (
    EntityType,
    FunctionEntity,
    Language,
    SourceLocation,
)

def create_function_entity(
    entity_id: str = "test::func",
    name: str = "func",
    source_code: str = "func test() {}",
) -> FunctionEntity:
    """Helper to create function entities for tests."""
    return FunctionEntity(
        id=entity_id,
        name=name,
        entity_type=EntityType.FUNCTION,
        language=Language.GO,
        location=SourceLocation(
            file_path=Path("/test.go"),
            start_line=1,
            end_line=2,
        ),
        source_code=source_code,
    )

# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_cache_dir(tmp_path):
    """Create a temporary cache directory."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return cache_dir

@pytest.fixture
def cache(temp_cache_dir):
    """Create a cache instance."""
    return AnalysisCache(cache_dir=temp_cache_dir)

@pytest.fixture
def cache_with_model(temp_cache_dir):
    """Create a cache instance with model name."""
    return AnalysisCache(cache_dir=temp_cache_dir, model="test-model")

@pytest.fixture
def cache_with_ttl(temp_cache_dir):
    """Create a cache instance with TTL."""
    return AnalysisCache(cache_dir=temp_cache_dir, ttl_seconds=60.0)

@pytest.fixture
def sample_entity():
    """Create a sample code entity."""
    return FunctionEntity(
        id="test::module::my_function",
        name="my_function",
        entity_type=EntityType.FUNCTION,
        language=Language.GO,
        location=SourceLocation(
            file_path=Path("/test/module.go"),
            start_line=10,
            end_line=20,
        ),
        docstring="A test function",
        source_code="func myFunction(x int) int {\n    return x * 2\n}",
    )

@pytest.fixture
def sample_summary():
    """Create a sample entity summary."""
    return EntitySummary(
        entity_id="test::module::my_function",
        summary="This function doubles the input value.",
        purpose="Multiply input by 2",
        domain="math",
        key_behaviors=["multiplication"],
        dependencies_used=[],
        input_tokens=100,
        output_tokens=50,
        model="test-model",
        code_hash="abc123",
    )

@pytest.fixture
def another_summary():
    """Create another sample summary."""
    return EntitySummary(
        entity_id="test::module::another_function",
        summary="Adds two numbers.",
        purpose="Addition operation",
        domain="math",
        key_behaviors=["addition"],
        dependencies_used=["my_function"],
    )

# =============================================================================
# CacheEntry Tests
# =============================================================================

class TestCacheEntry:
    """Tests for CacheEntry dataclass."""

    def test_create_entry(self):
        """Test creating a cache entry."""
        entry = CacheEntry(
            entity_id="test::entity",
            code_hash="abc123def456",
            timestamp=time.time(),
            model="qwen3:14b",
        )
        assert entry.entity_id == "test::entity"
        assert entry.code_hash == "abc123def456"
        assert entry.model == "qwen3:14b"
        assert entry.version == "1.0"

    def test_serialize_deserialize(self):
        """Test serialization round-trip."""
        original = CacheEntry(
            entity_id="test::entity",
            code_hash="abc123",
            timestamp=1234567890.123,
            model="test-model",
            version="1.0",
        )

        data = original.to_dict()
        restored = CacheEntry.from_dict(data)

        assert restored.entity_id == original.entity_id
        assert restored.code_hash == original.code_hash
        assert restored.timestamp == original.timestamp
        assert restored.model == original.model
        assert restored.version == original.version

# =============================================================================
# AnalysisCache Initialization Tests
# =============================================================================

class TestAnalysisCacheInit:
    """Tests for cache initialization."""

    def test_create_cache_creates_dirs(self, tmp_path):
        """Test that cache creates necessary directories."""
        cache_dir = tmp_path / "new_cache"
        assert not cache_dir.exists()

        cache = AnalysisCache(cache_dir=cache_dir)

        assert cache_dir.exists()
        assert (cache_dir / "summaries").exists()

    def test_create_cache_with_model(self, temp_cache_dir):
        """Test creating cache with model name."""
        cache = AnalysisCache(cache_dir=temp_cache_dir, model="my-model")
        assert cache.model == "my-model"

    def test_create_cache_with_ttl(self, temp_cache_dir):
        """Test creating cache with TTL."""
        cache = AnalysisCache(cache_dir=temp_cache_dir, ttl_seconds=3600)
        assert cache.ttl_seconds == 3600

    def test_load_empty_index(self, temp_cache_dir):
        """Test loading when no index exists."""
        cache = AnalysisCache(cache_dir=temp_cache_dir)
        assert len(cache._index) == 0

    def test_load_existing_index(self, temp_cache_dir):
        """Test loading existing index."""
        # Create an index file
        index_data = {
            "version": "1.0",
            "entries": {
                "test::entity": {
                    "entity_id": "test::entity",
                    "code_hash": "abc123",
                    "timestamp": time.time(),
                    "model": "",
                    "version": "1.0",
                }
            },
        }
        with open(temp_cache_dir / "cache_index.json", "w") as f:
            json.dump(index_data, f)

        cache = AnalysisCache(cache_dir=temp_cache_dir)
        assert len(cache._index) == 1
        assert "test::entity" in cache._index

    def test_clear_on_version_mismatch(self, temp_cache_dir):
        """Test that cache is cleared on version mismatch."""
        # Create an index with old version
        index_data = {
            "version": "0.9",  # Old version
            "entries": {"test::entity": {"entity_id": "test::entity"}},
        }
        with open(temp_cache_dir / "cache_index.json", "w") as f:
            json.dump(index_data, f)

        cache = AnalysisCache(cache_dir=temp_cache_dir)
        assert len(cache._index) == 0  # Should be cleared

# =============================================================================
# Hash Computation Tests
# =============================================================================

class TestHashComputation:
    """Tests for code hash computation."""

    def test_get_code_hash(self, cache, sample_entity):
        """Test computing code hash for entity."""
        hash1 = cache.get_code_hash(sample_entity)

        assert len(hash1) == 16
        assert hash1.isalnum()

    def test_hash_is_deterministic(self, cache, sample_entity):
        """Test that hash is consistent."""
        hash1 = cache.get_code_hash(sample_entity)
        hash2 = cache.get_code_hash(sample_entity)

        assert hash1 == hash2

    def test_hash_changes_with_content(self, cache):
        """Test that hash changes when code changes."""
        entity1 = create_function_entity(source_code="func test() {}")
        entity2 = create_function_entity(source_code="func test() { return 42 }")

        hash1 = cache.get_code_hash(entity1)
        hash2 = cache.get_code_hash(entity2)

        assert hash1 != hash2

    def test_hash_ignores_whitespace_variations(self, cache):
        """Test that hash normalizes whitespace."""
        entity1 = create_function_entity(source_code="func test() {\n    pass\n}")
        entity2 = create_function_entity(source_code="func test() {\n        pass\n}")

        hash1 = cache.get_code_hash(entity1)
        hash2 = cache.get_code_hash(entity2)

        assert hash1 == hash2  # Should be same after normalization

    def test_get_code_hash_from_string(self, cache):
        """Test computing hash from raw string."""
        code = "def hello(): pass"
        hash1 = cache.get_code_hash_from_string(code)
        hash2 = cache.get_code_hash_from_string(code, "function", "hello")

        assert len(hash1) == 16
        assert hash1 != hash2  # Different because of entity_type and name

# =============================================================================
# Cache Operations Tests
# =============================================================================

class TestCacheOperations:
    """Tests for basic cache operations."""

    def test_cache_and_retrieve_summary(self, cache, sample_summary):
        """Test caching and retrieving a summary."""
        code_hash = "test_hash_123"

        # Cache the summary
        cache.cache_summary(sample_summary, code_hash)

        # Retrieve it
        retrieved = cache.get_cached_summary(sample_summary.entity_id, code_hash)

        assert retrieved is not None
        assert retrieved.entity_id == sample_summary.entity_id
        assert retrieved.summary == sample_summary.summary
        assert retrieved.purpose == sample_summary.purpose

    def test_cache_miss_on_wrong_hash(self, cache, sample_summary):
        """Test that wrong hash returns None."""
        cache.cache_summary(sample_summary, "original_hash")

        # Try to retrieve with different hash
        retrieved = cache.get_cached_summary(sample_summary.entity_id, "different_hash")

        assert retrieved is None

    def test_cache_miss_on_unknown_entity(self, cache):
        """Test that unknown entity returns None."""
        retrieved = cache.get_cached_summary("unknown::entity", "any_hash")
        assert retrieved is None

    def test_has_cached(self, cache, sample_summary):
        """Test checking if entity is cached."""
        assert not cache.has_cached(sample_summary.entity_id)

        cache.cache_summary(sample_summary, "hash")

        assert cache.has_cached(sample_summary.entity_id)

    def test_get_entry_info(self, cache, sample_summary):
        """Test getting entry metadata."""
        cache.cache_summary(sample_summary, "test_hash")

        info = cache.get_entry_info(sample_summary.entity_id)

        assert info is not None
        assert info["entity_id"] == sample_summary.entity_id
        assert info["code_hash"] == "test_hash"
        assert "timestamp" in info
        assert "age_seconds" in info

    def test_get_entry_info_missing(self, cache):
        """Test getting info for missing entry."""
        info = cache.get_entry_info("missing::entity")
        assert info is None

# =============================================================================
# Invalidation Tests
# =============================================================================

class TestInvalidation:
    """Tests for cache invalidation."""

    def test_invalidate_single_entry(self, cache, sample_summary):
        """Test invalidating a single entry."""
        cache.cache_summary(sample_summary, "hash")
        assert cache.has_cached(sample_summary.entity_id)

        result = cache.invalidate(sample_summary.entity_id)

        assert result is True
        assert not cache.has_cached(sample_summary.entity_id)

    def test_invalidate_missing_entry(self, cache):
        """Test invalidating non-existent entry."""
        result = cache.invalidate("missing::entity")
        assert result is False

    def test_invalidate_dependents(self, cache, sample_summary, another_summary):
        """Test invalidating dependent entries."""
        # Cache both summaries
        cache.cache_summary(sample_summary, "hash1")
        cache.cache_summary(another_summary, "hash2")

        # Mock function that returns dependents
        def get_dependents(entity_id):
            if entity_id == sample_summary.entity_id:
                return [another_summary.entity_id]
            return []

        # Invalidate dependents of sample_summary
        invalidated = cache.invalidate_dependents(
            sample_summary.entity_id,
            get_dependents,
        )

        assert another_summary.entity_id in invalidated
        assert not cache.has_cached(another_summary.entity_id)
        # Original should still be there
        assert cache.has_cached(sample_summary.entity_id)

    def test_invalidate_cascade(self, cache, sample_summary, another_summary):
        """Test cascading invalidation."""
        # Create a chain: A -> B -> C
        summary_a = sample_summary
        summary_b = another_summary
        summary_c = EntitySummary(
            entity_id="test::third_entity",
            summary="Third entity",
            purpose="Testing cascade",
            domain="test",
        )

        cache.cache_summary(summary_a, "hash_a")
        cache.cache_summary(summary_b, "hash_b")
        cache.cache_summary(summary_c, "hash_c")

        def get_dependents(entity_id):
            deps = {
                summary_a.entity_id: [summary_b.entity_id],
                summary_b.entity_id: [summary_c.entity_id],
            }
            return deps.get(entity_id, [])

        # Cascade from A
        invalidated = cache.invalidate_cascade(summary_a.entity_id, get_dependents)

        assert summary_a.entity_id in invalidated
        assert summary_b.entity_id in invalidated
        assert summary_c.entity_id in invalidated
        assert len(cache._index) == 0

# =============================================================================
# TTL Tests
# =============================================================================

class TestTTL:
    """Tests for time-to-live functionality."""

    def test_ttl_not_expired(self, cache_with_ttl, sample_summary):
        """Test that fresh entries are not expired."""
        cache_with_ttl.cache_summary(sample_summary, "hash")

        retrieved = cache_with_ttl.get_cached_summary(sample_summary.entity_id, "hash")
        assert retrieved is not None

    def test_ttl_expired(self, temp_cache_dir, sample_summary):
        """Test that old entries are treated as expired."""
        cache = AnalysisCache(cache_dir=temp_cache_dir, ttl_seconds=0.1)
        cache.cache_summary(sample_summary, "hash")

        # Wait for TTL to expire
        time.sleep(0.2)

        retrieved = cache.get_cached_summary(sample_summary.entity_id, "hash")
        assert retrieved is None

    def test_cleanup_expired(self, temp_cache_dir, sample_summary):
        """Test cleanup of expired entries."""
        cache = AnalysisCache(cache_dir=temp_cache_dir, ttl_seconds=0.1)
        cache.cache_summary(sample_summary, "hash")

        time.sleep(0.2)

        removed = cache.cleanup_expired()
        assert removed == 1
        assert len(cache._index) == 0

# =============================================================================
# Model Filtering Tests
# =============================================================================

class TestModelFiltering:
    """Tests for model-based cache filtering."""

    def test_model_match(self, cache_with_model, sample_summary):
        """Test cache hit when model matches."""
        # First update summary to match model
        sample_summary.model = "test-model"

        # Manually set entry model (normally done by cache_summary)
        cache_with_model.cache_summary(sample_summary, "hash")

        retrieved = cache_with_model.get_cached_summary(sample_summary.entity_id, "hash")
        assert retrieved is not None

    def test_model_mismatch(self, temp_cache_dir, sample_summary):
        """Test cache miss when model doesn't match."""
        # Cache with one model
        cache1 = AnalysisCache(cache_dir=temp_cache_dir, model="model-a")
        cache1.cache_summary(sample_summary, "hash")

        # Try to retrieve with different model
        cache2 = AnalysisCache(cache_dir=temp_cache_dir, model="model-b")
        retrieved = cache2.get_cached_summary(sample_summary.entity_id, "hash")

        assert retrieved is None

# =============================================================================
# Batch Operations Tests
# =============================================================================

class TestBatchOperations:
    """Tests for batch cache operations."""

    def test_batch_cache_summaries(self, cache, sample_summary, another_summary):
        """Test caching multiple summaries at once."""
        summaries = [
            (sample_summary, "hash1"),
            (another_summary, "hash2"),
        ]

        count = cache.batch_cache_summaries(summaries)

        assert count == 2
        assert cache.has_cached(sample_summary.entity_id)
        assert cache.has_cached(another_summary.entity_id)

    def test_batch_cache_is_efficient(self, cache):
        """Test that batch caching saves index once."""
        summaries = []
        for i in range(10):
            summary = EntitySummary(
                entity_id=f"test::entity_{i}",
                summary=f"Summary {i}",
                purpose=f"Purpose {i}",
                domain="test",
            )
            summaries.append((summary, f"hash_{i}"))

        count = cache.batch_cache_summaries(summaries)

        assert count == 10
        # Verify all are cached
        for i in range(10):
            assert cache.has_cached(f"test::entity_{i}")

# =============================================================================
# Statistics and Cleanup Tests
# =============================================================================

class TestStatisticsAndCleanup:
    """Tests for cache statistics and cleanup."""

    def test_get_cache_stats(self, cache, sample_summary, another_summary):
        """Test getting cache statistics."""
        cache.cache_summary(sample_summary, "hash1")
        cache.cache_summary(another_summary, "hash2")

        stats = cache.get_cache_stats()

        assert stats["total_entries"] == 2
        assert "cache_dir" in stats
        assert "model" in stats

    def test_clear_cache(self, cache, sample_summary, another_summary):
        """Test clearing entire cache."""
        cache.cache_summary(sample_summary, "hash1")
        cache.cache_summary(another_summary, "hash2")

        count = cache.clear()

        assert count == 2
        assert len(cache._index) == 0
        assert not cache.has_cached(sample_summary.entity_id)

# =============================================================================
# Persistence Tests
# =============================================================================

class TestPersistence:
    """Tests for cache persistence across instances."""

    def test_persistence_across_instances(self, temp_cache_dir, sample_summary):
        """Test that cache persists across instances."""
        # Cache with first instance
        cache1 = AnalysisCache(cache_dir=temp_cache_dir)
        cache1.cache_summary(sample_summary, "persistent_hash")

        # Create new instance
        cache2 = AnalysisCache(cache_dir=temp_cache_dir)

        # Should be able to retrieve
        retrieved = cache2.get_cached_summary(sample_summary.entity_id, "persistent_hash")
        assert retrieved is not None
        assert retrieved.entity_id == sample_summary.entity_id

    def test_summary_files_created(self, temp_cache_dir, sample_summary):
        """Test that summary files are created on disk."""
        cache = AnalysisCache(cache_dir=temp_cache_dir)
        cache.cache_summary(sample_summary, "hash")

        # Check that summary file exists
        summaries_dir = temp_cache_dir / "summaries"
        summary_files = list(summaries_dir.glob("*.json"))
        assert len(summary_files) == 1

    def test_index_file_created(self, temp_cache_dir, sample_summary):
        """Test that index file is created."""
        cache = AnalysisCache(cache_dir=temp_cache_dir)
        cache.cache_summary(sample_summary, "hash")

        index_path = temp_cache_dir / "cache_index.json"
        assert index_path.exists()

        with open(index_path) as f:
            data = json.load(f)
        assert "version" in data
        assert "entries" in data

# =============================================================================
# Edge Cases Tests
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_source_code(self, cache):
        """Test handling entity with no source code."""
        entity = create_function_entity(
            entity_id="test::empty",
            name="empty",
            source_code="",
        )

        hash_val = cache.get_code_hash(entity)
        assert len(hash_val) == 16

    def test_none_source_code(self, cache):
        """Test handling entity with None source code."""
        entity = FunctionEntity(
            id="test::none",
            name="none",
            entity_type=EntityType.FUNCTION,
            language=Language.GO,
            location=SourceLocation(
                file_path=Path("/test.go"),
                start_line=1,
                end_line=1,
            ),
            source_code=None,
        )

        hash_val = cache.get_code_hash(entity)
        assert len(hash_val) == 16

    def test_special_characters_in_entity_id(self, cache, sample_summary):
        """Test handling entity IDs with special characters."""
        sample_summary.entity_id = "test::module::Class<T>::method(int, str)"

        cache.cache_summary(sample_summary, "hash")

        retrieved = cache.get_cached_summary(sample_summary.entity_id, "hash")
        assert retrieved is not None

    def test_unicode_in_summary(self, cache):
        """Test handling unicode content in summary."""
        summary = EntitySummary(
            entity_id="test::unicode",
            summary="Функция для работы с данными 数据处理",
            purpose="处理数据 и обработка",
            domain="интернационализация",
        )

        cache.cache_summary(summary, "hash")

        retrieved = cache.get_cached_summary(summary.entity_id, "hash")
        assert retrieved is not None
        assert "数据" in retrieved.summary

    def test_large_summary(self, cache):
        """Test handling large summary content."""
        summary = EntitySummary(
            entity_id="test::large",
            summary="x" * 100000,  # 100KB of text
            purpose="Testing large content",
            domain="test",
            key_behaviors=["behavior"] * 1000,
        )

        cache.cache_summary(summary, "hash")

        retrieved = cache.get_cached_summary(summary.entity_id, "hash")
        assert retrieved is not None
        assert len(retrieved.summary) == 100000
