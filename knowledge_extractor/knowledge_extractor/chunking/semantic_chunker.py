"""Semantic chunker for prose documents."""

import re
from typing import List

from ..parsers.base import ContentType, ParsedDocument
from .base import AbstractChunker, Chunk, ChunkType


class SemanticChunker(AbstractChunker):
    """Split documents by semantic boundaries (headers, paragraphs)."""

    def __init__(
        self,
        min_chunk_size: int = 200,
        max_chunk_size: int = 1500,
        overlap_sentences: int = 2,
    ):
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.overlap_sentences = overlap_sentences

        # Patterns for section boundaries
        self.section_patterns = [
            r"^#{1,3}\s+",  # Markdown headers
            r"^\d+\.\s+[А-ЯA-Z]",  # Numbered sections "1. Title"
            r"^[А-ЯA-Z][А-Яа-яA-Za-z\s]{5,}:$",  # "Title:" format
            r"^(?:Вопрос|Ответ|Q|A)[:\s]+",  # Q&A markers
        ]

    def supports(self, content_type: ContentType) -> bool:
        return content_type in (ContentType.PROSE, ContentType.MIXED)

    def chunk(self, document: ParsedDocument) -> List[Chunk]:
        """Split document into semantic chunks."""
        chunks = []

        # If document has pre-split sections, use them
        if document.sections and len(document.sections) > 1:
            for section in document.sections:
                if len(section.strip()) >= self.min_chunk_size:
                    chunks.append(
                        Chunk(
                            text=section.strip(),
                            chunk_type=ChunkType.SECTION,
                            source_file=document.source_file,
                        )
                    )
                elif section.strip():
                    # Small section - will be merged later
                    chunks.append(
                        Chunk(
                            text=section.strip(),
                            chunk_type=ChunkType.PARAGRAPH,
                            source_file=document.source_file,
                        )
                    )
        else:
            # Split raw text
            chunks = self._split_text(document.raw_text, document.source_file)

        # Add context to chunks
        chunks = self._add_context(chunks)

        # Merge small chunks
        chunks = self._merge_small_chunks(chunks)

        return chunks

    def _split_text(self, text: str, source_file: str) -> List[Chunk]:
        """Split text into chunks by semantic boundaries."""
        chunks = []
        paragraphs = self._split_paragraphs(text)

        current_chunk = []
        current_size = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # Check if this is a section boundary
            is_boundary = self._is_section_boundary(para)

            if is_boundary and current_chunk:
                # Save current chunk
                chunk_text = "\n\n".join(current_chunk)
                if len(chunk_text) >= self.min_chunk_size:
                    chunks.append(
                        Chunk(
                            text=chunk_text,
                            chunk_type=ChunkType.SECTION,
                            source_file=source_file,
                        )
                    )
                current_chunk = []
                current_size = 0

            current_chunk.append(para)
            current_size += len(para)

            # If chunk is too large, split
            if current_size >= self.max_chunk_size:
                chunk_text = "\n\n".join(current_chunk)
                chunks.append(
                    Chunk(
                        text=chunk_text,
                        chunk_type=ChunkType.SECTION,
                        source_file=source_file,
                    )
                )
                # Keep overlap
                current_chunk = current_chunk[-self.overlap_sentences:] if self.overlap_sentences else []
                current_size = sum(len(p) for p in current_chunk)

        # Add remaining
        if current_chunk:
            chunk_text = "\n\n".join(current_chunk)
            if chunk_text.strip():
                chunks.append(
                    Chunk(
                        text=chunk_text,
                        chunk_type=ChunkType.PARAGRAPH,
                        source_file=source_file,
                    )
                )

        return chunks

    def _split_paragraphs(self, text: str) -> List[str]:
        """Split text into paragraphs."""
        # Split by double newlines
        paragraphs = re.split(r"\n\n+", text)
        return [p.strip() for p in paragraphs if p.strip()]

    def _is_section_boundary(self, text: str) -> bool:
        """Check if text starts a new section."""
        for pattern in self.section_patterns:
            if re.match(pattern, text, re.MULTILINE):
                return True
        return False

    def _add_context(self, chunks: List[Chunk]) -> List[Chunk]:
        """Add surrounding context to each chunk."""
        for i, chunk in enumerate(chunks):
            context_parts = []

            # Previous chunk summary
            if i > 0:
                prev_text = chunks[i - 1].text[:200]
                context_parts.append(f"[Предыдущее]: {prev_text}...")

            # Next chunk summary
            if i < len(chunks) - 1:
                next_text = chunks[i + 1].text[:200]
                context_parts.append(f"[Следующее]: {next_text}...")

            chunk.context = "\n".join(context_parts)

        return chunks

    def _merge_small_chunks(self, chunks: List[Chunk]) -> List[Chunk]:
        """Merge chunks smaller than min_chunk_size."""
        if not chunks:
            return []

        merged = []
        current = None

        for chunk in chunks:
            if current is None:
                current = Chunk(
                    text=chunk.text,
                    chunk_type=chunk.chunk_type,
                    source_file=chunk.source_file,
                    context=chunk.context,
                )
            elif len(current.text) < self.min_chunk_size:
                # Merge with current
                current.text += "\n\n" + chunk.text
            elif len(chunk.text) < self.min_chunk_size:
                # Merge small chunk into current
                current.text += "\n\n" + chunk.text
            else:
                merged.append(current)
                current = Chunk(
                    text=chunk.text,
                    chunk_type=chunk.chunk_type,
                    source_file=chunk.source_file,
                    context=chunk.context,
                )

        if current and current.text.strip():
            merged.append(current)

        return merged
