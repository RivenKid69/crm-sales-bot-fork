"""Semantic deduplication using embeddings."""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from ..extraction.schemas import ExtractedSection

logger = logging.getLogger(__name__)


@dataclass
class DeduplicationResult:
    """Result of deduplication."""

    kept_sections: List[ExtractedSection]
    merged_pairs: List[Tuple[ExtractedSection, ExtractedSection]] = field(default_factory=list)
    removed_sections: List[ExtractedSection] = field(default_factory=list)
    similarity_matrix: Optional[np.ndarray] = None

    @property
    def removed_count(self) -> int:
        return len(self.removed_sections)

    @property
    def merge_count(self) -> int:
        return len(self.merged_pairs)


class SemanticDeduplicator:
    """Deduplicate sections based on semantic similarity."""

    def __init__(
        self,
        similarity_threshold: float = 0.85,
        embedder_model: str = "ai-forever/ru-en-RoSBERTa",
        merge_strategy: str = "longest",
    ):
        """
        Initialize deduplicator.

        Args:
            similarity_threshold: Cosine similarity threshold for considering duplicates
            embedder_model: Sentence-transformers model for embeddings
            merge_strategy: "longest" (keep longest facts) or "highest_priority"
        """
        self.similarity_threshold = similarity_threshold
        self.embedder_model = embedder_model
        self.merge_strategy = merge_strategy
        self._embedder = None

    def _get_embedder(self):
        """Lazy load embedder."""
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer

                logger.info(f"Loading embedder: {self.embedder_model}")
                self._embedder = SentenceTransformer(self.embedder_model)
            except ImportError:
                raise ImportError(
                    "sentence-transformers not installed. Run: pip install sentence-transformers"
                )
        return self._embedder

    def deduplicate(self, sections: List[ExtractedSection]) -> DeduplicationResult:
        """Find and merge duplicate sections."""
        if len(sections) <= 1:
            return DeduplicationResult(kept_sections=sections)

        logger.info(f"Deduplicating {len(sections)} sections")

        # Get embeddings
        embedder = self._get_embedder()
        texts = [s.facts for s in sections]
        embeddings = embedder.encode(texts, show_progress_bar=False)

        # Compute similarity matrix
        similarity_matrix = self._compute_similarity_matrix(embeddings)

        # Find clusters of similar sections
        clusters = self._find_clusters(similarity_matrix)

        # Process clusters
        kept = []
        merged_pairs = []
        removed = []

        for cluster_indices in clusters:
            if len(cluster_indices) == 1:
                kept.append(sections[cluster_indices[0]])
            else:
                # Multiple similar sections - merge
                cluster_sections = [sections[i] for i in cluster_indices]
                best = self._select_best(cluster_sections)
                merged = self._merge_sections(best, cluster_sections)

                kept.append(merged)
                for s in cluster_sections:
                    if s != best:
                        merged_pairs.append((merged, s))
                        removed.append(s)

        logger.info(f"Dedup: {len(kept)} kept, {len(removed)} removed")

        return DeduplicationResult(
            kept_sections=kept,
            merged_pairs=merged_pairs,
            removed_sections=removed,
            similarity_matrix=similarity_matrix,
        )

    def _compute_similarity_matrix(self, embeddings: np.ndarray) -> np.ndarray:
        """Compute cosine similarity matrix."""
        # Normalize
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)  # Avoid division by zero
        normalized = embeddings / norms

        # Cosine similarity
        return np.dot(normalized, normalized.T)

    def _find_clusters(self, similarity_matrix: np.ndarray) -> List[List[int]]:
        """Find clusters of similar items using agglomerative approach."""
        n = similarity_matrix.shape[0]
        assigned = set()
        clusters = []

        for i in range(n):
            if i in assigned:
                continue

            # Find all similar items
            cluster = [i]
            assigned.add(i)

            for j in range(i + 1, n):
                if j in assigned:
                    continue
                if similarity_matrix[i, j] >= self.similarity_threshold:
                    cluster.append(j)
                    assigned.add(j)

            clusters.append(cluster)

        return clusters

    def _select_best(self, sections: List[ExtractedSection]) -> ExtractedSection:
        """Select best section from cluster."""
        if self.merge_strategy == "longest":
            return max(sections, key=lambda s: len(s.facts))
        elif self.merge_strategy == "highest_priority":
            return max(sections, key=lambda s: s.priority)
        else:
            return sections[0]

    def _merge_sections(
        self,
        target: ExtractedSection,
        sources: List[ExtractedSection],
    ) -> ExtractedSection:
        """Merge keywords from all sources into target."""
        # Collect all keywords
        all_keywords = set(target.keywords)
        for s in sources:
            all_keywords.update(s.keywords)

        # Limit keywords
        keywords_list = list(all_keywords)[:50]

        # Keep highest priority
        max_priority = max(s.priority for s in sources)

        return ExtractedSection(
            topic=target.topic,
            priority=max_priority,
            category=target.category,
            keywords=keywords_list,
            facts=target.facts,
        )


def quick_dedup_by_topic(sections: List[ExtractedSection]) -> List[ExtractedSection]:
    """Quick deduplication by exact topic match."""
    seen_topics = set()
    unique = []

    for section in sections:
        if section.topic not in seen_topics:
            seen_topics.add(section.topic)
            unique.append(section)

    return unique
