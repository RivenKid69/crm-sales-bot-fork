"""Hash-based caching for analysis results.

Provides incremental analysis by caching entity summaries based on code hashes.
When code changes, the cache is invalidated for that entity and its dependents.

Inspired by GitHub Copilot's layered caching strategy and Sourcegraph's
intelligent cache invalidation approach.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...indexer.models.entities import CodeEntity
from ...utils.logging import get_logger
from ..models import EntitySummary

logger = get_logger("cache")


@dataclass
class CacheEntry:
    """Entry in the analysis cache."""

    entity_id: str
    code_hash: str
    timestamp: float
    model: str = ""
    version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "entity_id": self.entity_id,
            "code_hash": self.code_hash,
            "timestamp": self.timestamp,
            "model": self.model,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CacheEntry":
        """Deserialize from dictionary."""
        return cls(
            entity_id=data["entity_id"],
            code_hash=data["code_hash"],
            timestamp=data["timestamp"],
            model=data.get("model", ""),
            version=data.get("version", "1.0"),
        )


class AnalysisCache:
    """Cache for code analysis results.

    Features:
    - Hash-based invalidation (code content changes)
    - Dependency-aware invalidation (dependents invalidated when dependency changes)
    - Model-aware caching (different models have separate cache entries)
    - TTL support for time-based expiration
    """

    VERSION = "1.0"

    def __init__(
        self,
        cache_dir: Path,
        model: str = "",
        ttl_seconds: float | None = None,
    ):
        """Initialize the cache.

        Args:
            cache_dir: Directory to store cache files
            model: Model name for cache segregation
            ttl_seconds: Optional time-to-live for cache entries
        """
        self.cache_dir = cache_dir
        self.model = model
        self.ttl_seconds = ttl_seconds

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._summaries_dir = self.cache_dir / "summaries"
        self._summaries_dir.mkdir(exist_ok=True)

        self._index: dict[str, CacheEntry] = {}
        self._load_index()

    def _get_index_path(self) -> Path:
        """Get path to the cache index file."""
        return self.cache_dir / "cache_index.json"

    def _load_index(self) -> None:
        """Load the cache index from disk."""
        index_path = self._get_index_path()
        if index_path.exists():
            try:
                with open(index_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Check version compatibility
                if data.get("version") != self.VERSION:
                    logger.info("Cache version mismatch, clearing cache")
                    self._index = {}
                    return

                self._index = {
                    k: CacheEntry.from_dict(v)
                    for k, v in data.get("entries", {}).items()
                }
                logger.debug(f"Loaded {len(self._index)} cache entries")
            except Exception as e:
                logger.warning(f"Failed to load cache index: {e}")
                self._index = {}
        else:
            self._index = {}

    def _save_index(self) -> None:
        """Save the cache index to disk."""
        index_path = self._get_index_path()
        data = {
            "version": self.VERSION,
            "entries": {k: v.to_dict() for k, v in self._index.items()},
        }
        try:
            with open(index_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save cache index: {e}")

    def _get_summary_path(self, entity_id: str) -> Path:
        """Get path for storing a summary file."""
        # Use hash of entity_id for flat directory structure
        safe_id = hashlib.md5(entity_id.encode()).hexdigest()
        return self._summaries_dir / f"{safe_id}.json"

    def get_code_hash(self, entity: CodeEntity) -> str:
        """Compute hash of entity's source code.

        The hash is normalized to ignore whitespace variations,
        making it resistant to formatting-only changes.

        Args:
            entity: Code entity to hash

        Returns:
            16-character hex hash string
        """
        content = entity.source_code or ""

        # Normalize: collapse whitespace, strip leading/trailing
        normalized = " ".join(content.split())

        # Include entity type and name for uniqueness
        hash_input = f"{entity.entity_type.value}:{entity.name}:{normalized}"

        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    def get_code_hash_from_string(self, code: str, entity_type: str = "", name: str = "") -> str:
        """Compute hash from raw code string.

        Args:
            code: Source code string
            entity_type: Optional entity type for uniqueness
            name: Optional entity name for uniqueness

        Returns:
            16-character hex hash string
        """
        normalized = " ".join(code.split())
        hash_input = f"{entity_type}:{name}:{normalized}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    def _is_expired(self, entry: CacheEntry) -> bool:
        """Check if a cache entry has expired."""
        if self.ttl_seconds is None:
            return False
        return (time.time() - entry.timestamp) > self.ttl_seconds

    def _is_model_match(self, entry: CacheEntry) -> bool:
        """Check if cache entry matches current model."""
        if not self.model:
            return True  # No model filtering
        return entry.model == self.model

    def get_cached_summary(
        self,
        entity_id: str,
        code_hash: str,
    ) -> EntitySummary | None:
        """Get cached summary if hash matches.

        Args:
            entity_id: Entity ID to look up
            code_hash: Expected code hash

        Returns:
            Cached EntitySummary if valid, None otherwise
        """
        entry = self._index.get(entity_id)

        if not entry:
            return None

        # Check hash match
        if entry.code_hash != code_hash:
            logger.debug(f"Cache miss for {entity_id}: hash mismatch")
            return None

        # Check TTL
        if self._is_expired(entry):
            logger.debug(f"Cache miss for {entity_id}: expired")
            return None

        # Check model match
        if not self._is_model_match(entry):
            logger.debug(f"Cache miss for {entity_id}: model mismatch")
            return None

        # Load and return the summary
        return self._load_summary(entity_id)

    def _load_summary(self, entity_id: str) -> EntitySummary | None:
        """Load a summary from disk."""
        summary_path = self._get_summary_path(entity_id)

        if not summary_path.exists():
            return None

        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return EntitySummary.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load summary for {entity_id}: {e}")
            return None

    def cache_summary(
        self,
        summary: EntitySummary,
        code_hash: str,
    ) -> None:
        """Cache a summary.

        Args:
            summary: Summary to cache
            code_hash: Code hash for this summary
        """
        # Update index
        self._index[summary.entity_id] = CacheEntry(
            entity_id=summary.entity_id,
            code_hash=code_hash,
            timestamp=time.time(),
            model=self.model,
            version=self.VERSION,
        )

        # Save summary file
        self._save_summary(summary)

        # Save index (batch saves might be more efficient for large operations)
        self._save_index()

        logger.debug(f"Cached summary for {summary.entity_id}")

    def _save_summary(self, summary: EntitySummary) -> None:
        """Save a summary to disk."""
        summary_path = self._get_summary_path(summary.entity_id)

        try:
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save summary for {summary.entity_id}: {e}")

    def invalidate(self, entity_id: str) -> bool:
        """Invalidate a single entity's cache.

        Args:
            entity_id: Entity to invalidate

        Returns:
            True if entry was found and invalidated
        """
        if entity_id in self._index:
            del self._index[entity_id]

            # Also remove summary file
            summary_path = self._get_summary_path(entity_id)
            if summary_path.exists():
                try:
                    summary_path.unlink()
                except OSError:
                    pass

            self._save_index()
            return True
        return False

    def invalidate_dependents(
        self,
        entity_id: str,
        get_dependents_fn,
    ) -> list[str]:
        """Invalidate cache for all entities that depend on this entity.

        When entity B depends on entity A, and A changes,
        B's summary might be outdated (it references A).

        Args:
            entity_id: Entity that changed
            get_dependents_fn: Function that returns list of dependent entity IDs.
                              Signature: (entity_id: str) -> list[str]

        Returns:
            List of invalidated entity IDs
        """
        try:
            dependent_ids = get_dependents_fn(entity_id)
        except Exception as e:
            logger.warning(f"Failed to get dependents for {entity_id}: {e}")
            return []

        invalidated: list[str] = []
        for dep_id in dependent_ids:
            if dep_id in self._index:
                del self._index[dep_id]
                invalidated.append(dep_id)

        if invalidated:
            self._save_index()
            logger.info(f"Invalidated {len(invalidated)} dependents of {entity_id}")

        return invalidated

    def invalidate_cascade(
        self,
        entity_id: str,
        get_dependents_fn,
        visited: set[str] | None = None,
    ) -> list[str]:
        """Recursively invalidate all transitive dependents.

        This performs a full cascade invalidation through the dependency graph.

        Args:
            entity_id: Entity that changed
            get_dependents_fn: Function to get dependent IDs
            visited: Set of already visited entities (for recursion)

        Returns:
            List of all invalidated entity IDs
        """
        if visited is None:
            visited = set()

        if entity_id in visited:
            return []

        visited.add(entity_id)
        invalidated: list[str] = []

        # Invalidate this entity
        if entity_id in self._index:
            del self._index[entity_id]
            invalidated.append(entity_id)

        # Recursively invalidate dependents
        try:
            dependent_ids = get_dependents_fn(entity_id)
            for dep_id in dependent_ids:
                invalidated.extend(
                    self.invalidate_cascade(dep_id, get_dependents_fn, visited)
                )
        except Exception:
            pass

        return invalidated

    def batch_cache_summaries(
        self,
        summaries: list[tuple[EntitySummary, str]],
    ) -> int:
        """Cache multiple summaries efficiently.

        Args:
            summaries: List of (summary, code_hash) tuples

        Returns:
            Number of summaries cached
        """
        count = 0
        for summary, code_hash in summaries:
            # Update index
            self._index[summary.entity_id] = CacheEntry(
                entity_id=summary.entity_id,
                code_hash=code_hash,
                timestamp=time.time(),
                model=self.model,
                version=self.VERSION,
            )
            # Save summary file
            self._save_summary(summary)
            count += 1

        # Save index once at the end
        self._save_index()
        logger.info(f"Batch cached {count} summaries")

        return count

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        now = time.time()
        expired = sum(
            1 for entry in self._index.values()
            if self.ttl_seconds and (now - entry.timestamp) > self.ttl_seconds
        )

        models: dict[str, int] = {}
        for entry in self._index.values():
            models[entry.model] = models.get(entry.model, 0) + 1

        return {
            "total_entries": len(self._index),
            "expired_entries": expired,
            "cache_dir": str(self.cache_dir),
            "model": self.model,
            "ttl_seconds": self.ttl_seconds,
            "entries_by_model": models,
        }

    def clear(self) -> int:
        """Clear all cache entries.

        Returns:
            Number of entries cleared
        """
        count = len(self._index)
        self._index.clear()

        # Remove all summary files
        for summary_file in self._summaries_dir.glob("*.json"):
            try:
                summary_file.unlink()
            except OSError:
                pass

        self._save_index()
        logger.info(f"Cleared {count} cache entries")

        return count

    def cleanup_expired(self) -> int:
        """Remove expired entries from cache.

        Returns:
            Number of entries removed
        """
        if self.ttl_seconds is None:
            return 0

        now = time.time()
        expired_ids = [
            entity_id
            for entity_id, entry in self._index.items()
            if (now - entry.timestamp) > self.ttl_seconds
        ]

        for entity_id in expired_ids:
            del self._index[entity_id]
            summary_path = self._get_summary_path(entity_id)
            if summary_path.exists():
                try:
                    summary_path.unlink()
                except OSError:
                    pass

        if expired_ids:
            self._save_index()
            logger.info(f"Cleaned up {len(expired_ids)} expired cache entries")

        return len(expired_ids)

    def has_cached(self, entity_id: str) -> bool:
        """Check if an entity has a cache entry (without validating hash).

        Args:
            entity_id: Entity ID to check

        Returns:
            True if entry exists
        """
        return entity_id in self._index

    def get_entry_info(self, entity_id: str) -> dict[str, Any] | None:
        """Get metadata about a cache entry.

        Args:
            entity_id: Entity ID to look up

        Returns:
            Entry metadata or None
        """
        entry = self._index.get(entity_id)
        if entry:
            return {
                "entity_id": entry.entity_id,
                "code_hash": entry.code_hash,
                "timestamp": entry.timestamp,
                "age_seconds": time.time() - entry.timestamp,
                "model": entry.model,
                "version": entry.version,
                "expired": self._is_expired(entry),
            }
        return None
