"""Main plagiarism detector combining multiple algorithms."""

from .models import PlagiarismReport, SimilarityMetrics
from .algorithms import (
    tokenize,
    ngram_similarity,
    jaccard_similarity,
    simhash_similarity,
    winnowing_similarity,
)
from ..config import settings


class PlagiarismDetector:
    """Plagiarism detector using multiple scientific algorithms.

    Combines results from:
    - N-gram overlap analysis
    - Jaccard similarity
    - SimHash (Charikar, 2002)
    - Winnowing (Schleimer et al., 2003)

    Each method has different strengths:
    - N-gram: Good for detecting phrase-level copying
    - Jaccard: Good for vocabulary similarity
    - SimHash: Efficient near-duplicate detection
    - Winnowing: Guaranteed detection of long common substrings
    """

    def __init__(
        self,
        ngram_size: int | None = None,
        shingle_size: int | None = None,
        uniqueness_threshold: float | None = None,
        weights: dict[str, float] | None = None,
    ):
        """Initialize detector.

        Args:
            ngram_size: Size of n-grams for analysis
            shingle_size: Size of shingles for winnowing
            uniqueness_threshold: Minimum uniqueness (0-1) to pass
            weights: Custom weights for each algorithm
        """
        self.ngram_size = ngram_size or settings.ngram_size
        self.shingle_size = shingle_size or settings.shingle_size
        self.uniqueness_threshold = uniqueness_threshold or settings.min_uniqueness_threshold

        # Weights calibrated to match text.ru / Advego / ETXT behavior
        # These services focus on phrase matching, not semantic similarity
        self.weights = weights or {
            "ngram": 0.55,      # Primary: phrase-level plagiarism
            "jaccard": 0.15,    # Secondary: vocabulary overlap
            "simhash": 0.00,    # Disabled: semantic similarity not used by real services
            "winnowing": 0.30,  # Shingle-based fingerprinting
        }

    def analyze(self, original: str, rewritten: str) -> PlagiarismReport:
        """Analyze similarity between original and rewritten texts.

        Args:
            original: Original source text
            rewritten: Rewritten/paraphrased text

        Returns:
            PlagiarismReport with detailed metrics
        """
        # Tokenize for word counts
        original_tokens = tokenize(original)
        rewritten_tokens = tokenize(rewritten)

        # Calculate individual similarities
        ngram_sim, common_count, total_orig, total_rewr = ngram_similarity(
            original, rewritten, self.ngram_size
        )
        jaccard_sim = jaccard_similarity(original, rewritten)
        simhash_sim = simhash_similarity(original, rewritten)
        winnowing_sim = winnowing_similarity(original, rewritten, self.shingle_size)

        metrics = SimilarityMetrics(
            ngram_similarity=ngram_sim,
            jaccard_similarity=jaccard_sim,
            simhash_similarity=simhash_sim,
            winnowing_similarity=winnowing_sim,
        )

        # Calculate weighted similarity
        weighted_similarity = (
            self.weights["ngram"] * ngram_sim
            + self.weights["jaccard"] * jaccard_sim
            + self.weights["simhash"] * simhash_sim
            + self.weights["winnowing"] * winnowing_sim
        )

        # Uniqueness is inverse of similarity
        uniqueness_score = (1 - weighted_similarity) * 100

        # Determine if passes threshold
        is_unique = uniqueness_score >= (self.uniqueness_threshold * 100)

        return PlagiarismReport(
            uniqueness_score=uniqueness_score,
            metrics=metrics,
            weighted_similarity=weighted_similarity,
            original_word_count=len(original_tokens),
            rewritten_word_count=len(rewritten_tokens),
            common_ngrams_count=common_count,
            total_ngrams_original=total_orig,
            total_ngrams_rewritten=total_rewr,
            is_unique=is_unique,
            threshold_used=self.uniqueness_threshold,
        )

    def quick_check(self, original: str, rewritten: str) -> bool:
        """Quick pass/fail check without detailed report.

        Args:
            original: Original source text
            rewritten: Rewritten text

        Returns:
            True if text passes uniqueness threshold
        """
        report = self.analyze(original, rewritten)
        return report.is_unique

    def get_similarity_breakdown(self, original: str, rewritten: str) -> dict[str, float]:
        """Get individual similarity scores.

        Args:
            original: Original text
            rewritten: Rewritten text

        Returns:
            Dictionary of algorithm names to similarity scores
        """
        ngram_sim, _, _, _ = ngram_similarity(original, rewritten, self.ngram_size)

        return {
            "ngram": ngram_sim,
            "jaccard": jaccard_similarity(original, rewritten),
            "simhash": simhash_similarity(original, rewritten),
            "winnowing": winnowing_similarity(original, rewritten, self.shingle_size),
        }
