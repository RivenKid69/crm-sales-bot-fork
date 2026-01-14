"""Q&A pairs chunker."""

from typing import List

from ..parsers.base import ContentType, ParsedDocument
from .base import AbstractChunker, Chunk, ChunkType


class QAChunker(AbstractChunker):
    """Chunk Q&A pairs - each pair becomes one chunk."""

    def __init__(self, group_similar: bool = False, max_pairs_per_chunk: int = 1):
        """
        Initialize QA chunker.

        Args:
            group_similar: Group similar Q&A pairs into one chunk
            max_pairs_per_chunk: Max Q&A pairs per chunk (1 = each pair is separate)
        """
        self.group_similar = group_similar
        self.max_pairs_per_chunk = max_pairs_per_chunk

    def supports(self, content_type: ContentType) -> bool:
        return content_type == ContentType.QA_PAIRS

    def chunk(self, document: ParsedDocument) -> List[Chunk]:
        """Convert Q&A pairs to chunks."""
        chunks = []

        if not document.qa_pairs:
            # Fallback: treat as prose
            from .semantic_chunker import SemanticChunker

            return SemanticChunker().chunk(document)

        for question, answer in document.qa_pairs:
            question = question.strip()
            answer = answer.strip()

            if not question or not answer:
                continue

            # Format as text
            text = f"Вопрос: {question}\n\nОтвет: {answer}"

            chunk = Chunk(
                text=text,
                chunk_type=ChunkType.QA_PAIR,
                source_file=document.source_file,
                question=question,
                answer=answer,
                metadata={"is_qa": True},
            )
            chunks.append(chunk)

        return chunks

    def chunk_grouped(self, document: ParsedDocument) -> List[Chunk]:
        """Group similar Q&A pairs into chunks."""
        if not document.qa_pairs:
            return []

        # Simple grouping by first words in question
        groups = {}

        for q, a in document.qa_pairs:
            # Get first significant word
            words = q.lower().split()
            key_words = [w for w in words if len(w) > 3]
            key = key_words[0] if key_words else "other"

            if key not in groups:
                groups[key] = []
            groups[key].append((q, a))

        chunks = []
        for key, pairs in groups.items():
            # Create chunk for group
            text_parts = []
            for q, a in pairs[: self.max_pairs_per_chunk]:
                text_parts.append(f"**{q}**\n{a}")

            text = "\n\n".join(text_parts)
            chunks.append(
                Chunk(
                    text=text,
                    chunk_type=ChunkType.QA_PAIR,
                    source_file=document.source_file,
                    metadata={"group_key": key, "pair_count": len(pairs)},
                )
            )

        return chunks
