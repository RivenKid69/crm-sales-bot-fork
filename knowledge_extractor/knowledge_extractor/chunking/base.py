"""Base chunking classes."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from ..parsers.base import ContentType, ParsedDocument


class ChunkType(Enum):
    """Type of chunk."""

    PARAGRAPH = "paragraph"
    SECTION = "section"
    QA_PAIR = "qa_pair"
    TABLE_ROW = "table_row"
    TABLE_BLOCK = "table_block"
    CHAT_THREAD = "chat_thread"


@dataclass
class Chunk:
    """Unit of text for processing."""

    text: str
    chunk_type: ChunkType
    source_file: str
    context: str = ""  # Surrounding text for understanding
    metadata: Dict = field(default_factory=dict)

    # For Q&A pairs
    question: Optional[str] = None
    answer: Optional[str] = None

    # For tables
    headers: Optional[List[str]] = None
    row_data: Optional[Dict] = None

    def __len__(self) -> int:
        return len(self.text)

    @property
    def is_qa(self) -> bool:
        return self.chunk_type == ChunkType.QA_PAIR and self.question and self.answer


class AbstractChunker(ABC):
    """Base chunker interface."""

    @abstractmethod
    def chunk(self, document: ParsedDocument) -> List[Chunk]:
        """Split document into chunks."""
        pass

    @abstractmethod
    def supports(self, content_type: ContentType) -> bool:
        """Check if chunker supports this content type."""
        pass


def merge_chunks(chunks: List[Chunk], max_size: int = 2000) -> List[Chunk]:
    """Merge small chunks into larger ones."""
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
                metadata=chunk.metadata.copy(),
            )
        elif len(current.text) + len(chunk.text) < max_size:
            # Merge
            current.text += "\n\n" + chunk.text
        else:
            merged.append(current)
            current = Chunk(
                text=chunk.text,
                chunk_type=chunk.chunk_type,
                source_file=chunk.source_file,
                metadata=chunk.metadata.copy(),
            )

    if current:
        merged.append(current)

    return merged
