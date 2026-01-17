"""Plagiarism detection module based on scientific methods."""

from .detector import PlagiarismDetector
from .models import PlagiarismReport, SimilarityMetrics

__all__ = ["PlagiarismDetector", "PlagiarismReport", "SimilarityMetrics"]
