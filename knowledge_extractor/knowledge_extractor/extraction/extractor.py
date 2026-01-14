"""Main knowledge extraction pipeline."""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Generator, List, Optional

from ..config import Config, ExtractionConfig
from ..llm.client import LLMClient, LLMError, LLMValidationError
from .keyword_generator import KeywordGenerator
from .prompts import SYSTEM_PROMPT, format_extract_prompt
from .schemas import ExtractedSection, FullExtractionResult
from .topic_generator import TopicGenerator

logger = logging.getLogger(__name__)


class ExtractionStatus(Enum):
    """Extraction status."""

    SUCCESS = "success"
    PARTIAL = "partial"  # Some fields missing
    RETRY_SCHEDULED = "retry"
    FAILED = "failed"
    SKIPPED = "skipped"  # Empty content


@dataclass
class ExtractionResult:
    """Result of extraction for one chunk."""

    chunk: "Chunk"
    status: ExtractionStatus
    section: Optional[ExtractedSection] = None
    error: Optional[str] = None
    retries: int = 0
    processing_time_ms: float = 0


@dataclass
class ExtractionStats:
    """Extraction statistics."""

    total_chunks: int = 0
    successful: int = 0
    partial: int = 0
    failed: int = 0
    skipped: int = 0
    total_time_s: float = 0

    @property
    def success_rate(self) -> float:
        processed = self.total_chunks - self.skipped
        if processed == 0:
            return 0.0
        return (self.successful + self.partial) / processed


class KnowledgeExtractor:
    """Main extraction pipeline."""

    MAX_RETRIES = 3
    MIN_CHUNK_LENGTH = 30

    def __init__(self, config: Config):
        self.config = config
        self.llm = LLMClient(config.llm)
        self.keyword_gen = KeywordGenerator(llm_client=self.llm)
        self.topic_gen = TopicGenerator()
        self.stats = ExtractionStats()
        self._failed_chunks: List["Chunk"] = []

    def extract_batch(
        self,
        chunks: List["Chunk"],
        on_progress: callable = None,
    ) -> Generator[ExtractionResult, None, None]:
        """
        Extract sections from batch of chunks.

        Yields results as they are processed for streaming progress.
        """
        self.stats.total_chunks = len(chunks)
        start_time = time.time()

        for i, chunk in enumerate(chunks):
            result = self._extract_with_retry(chunk)

            # Update stats
            if result.status == ExtractionStatus.SUCCESS:
                self.stats.successful += 1
            elif result.status == ExtractionStatus.PARTIAL:
                self.stats.partial += 1
            elif result.status == ExtractionStatus.FAILED:
                self.stats.failed += 1
                self._failed_chunks.append(chunk)
            elif result.status == ExtractionStatus.SKIPPED:
                self.stats.skipped += 1

            if on_progress:
                on_progress(i + 1, len(chunks), result)

            yield result

        self.stats.total_time_s = time.time() - start_time

    def _extract_with_retry(self, chunk: "Chunk") -> ExtractionResult:
        """Extract with retry logic."""
        start_time = time.time()

        # Skip empty chunks
        if not chunk.text or len(chunk.text.strip()) < self.MIN_CHUNK_LENGTH:
            return ExtractionResult(
                chunk=chunk,
                status=ExtractionStatus.SKIPPED,
                error="Chunk too short or empty",
            )

        last_error = None

        for attempt in range(self.MAX_RETRIES):
            try:
                section = self._do_extraction(chunk)

                return ExtractionResult(
                    chunk=chunk,
                    status=ExtractionStatus.SUCCESS,
                    section=section,
                    retries=attempt,
                    processing_time_ms=(time.time() - start_time) * 1000,
                )

            except LLMValidationError as e:
                logger.warning(f"Validation error on attempt {attempt + 1}: {e}")
                last_error = str(e)

                # Try simplified extraction
                if attempt == self.MAX_RETRIES - 1:
                    try:
                        section = self._do_simplified_extraction(chunk)
                        return ExtractionResult(
                            chunk=chunk,
                            status=ExtractionStatus.PARTIAL,
                            section=section,
                            retries=attempt + 1,
                            processing_time_ms=(time.time() - start_time) * 1000,
                        )
                    except Exception:
                        pass

            except LLMError as e:
                logger.warning(f"LLM error on attempt {attempt + 1}: {e}")
                last_error = str(e)
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(2**attempt)

            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                last_error = str(e)

        return ExtractionResult(
            chunk=chunk,
            status=ExtractionStatus.FAILED,
            error=last_error,
            retries=self.MAX_RETRIES,
            processing_time_ms=(time.time() - start_time) * 1000,
        )

    def _do_extraction(self, chunk: "Chunk") -> ExtractedSection:
        """Perform full extraction."""
        # Format prompt
        prompt = format_extract_prompt(
            chunk_text=chunk.text,
            context=getattr(chunk, "context", ""),
        )

        # Call LLM with structured output
        result = self.llm.generate_structured(
            prompt=prompt,
            schema=FullExtractionResult,
            system_prompt=SYSTEM_PROMPT,
        )

        # Generate unique topic
        topic = self.topic_gen.generate(
            text_hint=result.topic,
            category=result.category,
        )

        # Expand keywords
        keyword_set = self.keyword_gen.generate(
            primary_keywords=result.primary_keywords,
            synonyms=result.synonyms,
            question_phrases=result.question_phrases,
            text_context=chunk.text[:500],
        )

        # Build final section
        keywords = keyword_set.to_flat_list(max_count=self.config.extraction.max_keywords)

        # Ensure minimum keywords
        if len(keywords) < self.config.extraction.min_keywords:
            # Add more from primary if available
            for kw in result.primary_keywords:
                if kw.lower() not in keywords:
                    keywords.append(kw.lower())
                if len(keywords) >= self.config.extraction.min_keywords:
                    break

        return ExtractedSection(
            topic=topic,
            priority=result.priority,
            category=result.category,
            keywords=keywords,
            facts=result.facts,
        )

    def _do_simplified_extraction(self, chunk: "Chunk") -> ExtractedSection:
        """Simplified extraction for problematic chunks."""
        # Simple text-based extraction without full LLM structure
        text = chunk.text.strip()

        # Generate topic from first words
        first_words = " ".join(text.split()[:5])
        topic = self.topic_gen.generate(first_words, "general")

        # Extract basic keywords from text
        words = set(text.lower().split())
        keywords = [w for w in words if len(w) > 3 and w.isalpha()][:20]

        # Add question phrases
        keywords.extend(["что такое", "как работает", "сколько"])

        return ExtractedSection(
            topic=topic,
            priority=self.config.extraction.default_priority,
            category="faq",
            keywords=keywords,
            facts=text[:2000],
        )

    def get_failed_chunks(self) -> List["Chunk"]:
        """Get list of failed chunks for retry."""
        return self._failed_chunks

    def get_stats(self) -> ExtractionStats:
        """Get extraction statistics."""
        return self.stats

    def reset_stats(self):
        """Reset statistics."""
        self.stats = ExtractionStats()
        self._failed_chunks.clear()
        self.topic_gen.reset()
