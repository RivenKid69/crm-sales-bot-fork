"""Data models for plagiarism detection."""

from pydantic import BaseModel, Field


class SimilarityMetrics(BaseModel):
    """Individual similarity metrics."""

    ngram_similarity: float = Field(ge=0.0, le=1.0, description="N-gram overlap coefficient")
    jaccard_similarity: float = Field(ge=0.0, le=1.0, description="Jaccard similarity index")
    simhash_similarity: float = Field(ge=0.0, le=1.0, description="SimHash similarity (Charikar, 2002)")
    winnowing_similarity: float = Field(ge=0.0, le=1.0, description="Winnowing fingerprint similarity (Schleimer et al., 2003)")


class PlagiarismReport(BaseModel):
    """Complete plagiarism analysis report."""

    # Overall uniqueness score (0-100%)
    uniqueness_score: float = Field(ge=0.0, le=100.0, description="Overall uniqueness percentage")

    # Individual metrics
    metrics: SimilarityMetrics

    # Weighted similarity (0-1, lower is more unique)
    weighted_similarity: float = Field(ge=0.0, le=1.0)

    # Analysis details
    original_word_count: int
    rewritten_word_count: int
    common_ngrams_count: int
    total_ngrams_original: int
    total_ngrams_rewritten: int

    # Pass/Fail based on threshold
    is_unique: bool
    threshold_used: float

    def summary(self) -> str:
        """Generate human-readable summary."""
        status = "PASSED" if self.is_unique else "FAILED"
        return (
            f"Uniqueness: {self.uniqueness_score:.1f}% [{status}]\n"
            f"Threshold: {self.threshold_used * 100:.0f}%\n"
            f"---\n"
            f"N-gram similarity: {self.metrics.ngram_similarity * 100:.1f}%\n"
            f"Jaccard similarity: {self.metrics.jaccard_similarity * 100:.1f}%\n"
            f"SimHash similarity: {self.metrics.simhash_similarity * 100:.1f}%\n"
            f"Winnowing similarity: {self.metrics.winnowing_similarity * 100:.1f}%\n"
            f"---\n"
            f"Original words: {self.original_word_count}\n"
            f"Rewritten words: {self.rewritten_word_count}\n"
            f"Common n-grams: {self.common_ngrams_count}/{self.total_ngrams_original}"
        )
