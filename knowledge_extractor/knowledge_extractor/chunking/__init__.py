"""Chunking module."""

from .base import AbstractChunker, Chunk, ChunkType
from .semantic_chunker import SemanticChunker
from .qa_chunker import QAChunker
from .table_chunker import TableChunker

__all__ = [
    "AbstractChunker",
    "Chunk",
    "ChunkType",
    "SemanticChunker",
    "QAChunker",
    "TableChunker",
]


def get_chunker_for_content(content_type: str) -> AbstractChunker:
    """Get appropriate chunker for content type."""
    from ..parsers.base import ContentType

    if content_type == ContentType.QA_PAIRS:
        return QAChunker()
    elif content_type == ContentType.TABLE:
        return TableChunker()
    else:
        return SemanticChunker()
