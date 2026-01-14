"""Table data chunker."""

from typing import List

from ..parsers.base import ContentType, ParsedDocument
from .base import AbstractChunker, Chunk, ChunkType


class TableChunker(AbstractChunker):
    """Chunk tabular data."""

    def __init__(self, rows_per_chunk: int = 10, include_headers: bool = True):
        """
        Initialize table chunker.

        Args:
            rows_per_chunk: Number of rows per chunk
            include_headers: Include column headers in each chunk
        """
        self.rows_per_chunk = rows_per_chunk
        self.include_headers = include_headers

    def supports(self, content_type: ContentType) -> bool:
        return content_type == ContentType.TABLE

    def chunk(self, document: ParsedDocument) -> List[Chunk]:
        """Convert table data to chunks."""
        chunks = []

        if not document.tables:
            # Fallback: treat raw text as table-like
            return self._chunk_from_text(document)

        for table_idx, table in enumerate(document.tables):
            if not table or len(table) < 2:
                continue

            headers = table[0]
            rows = table[1:]

            # Split rows into chunks
            for i in range(0, len(rows), self.rows_per_chunk):
                chunk_rows = rows[i: i + self.rows_per_chunk]

                # Format as markdown table
                text = self._format_table_chunk(headers, chunk_rows)

                # Also format as key-value for context
                context = self._format_as_text(headers, chunk_rows)

                chunk = Chunk(
                    text=text,
                    chunk_type=ChunkType.TABLE_BLOCK,
                    source_file=document.source_file,
                    context=context,
                    headers=headers,
                    metadata={
                        "table_index": table_idx,
                        "row_start": i,
                        "row_count": len(chunk_rows),
                    },
                )
                chunks.append(chunk)

        return chunks

    def _format_table_chunk(self, headers: List[str], rows: List[List[str]]) -> str:
        """Format rows as markdown table."""
        lines = []

        # Header
        lines.append("| " + " | ".join(str(h) for h in headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")

        # Rows
        for row in rows:
            # Pad row if needed
            padded = list(row) + [""] * (len(headers) - len(row))
            lines.append("| " + " | ".join(str(c) for c in padded[: len(headers)]) + " |")

        return "\n".join(lines)

    def _format_as_text(self, headers: List[str], rows: List[List[str]]) -> str:
        """Format table as key-value text for LLM context."""
        lines = []

        for row in rows:
            row_text = []
            for i, header in enumerate(headers):
                if i < len(row) and row[i]:
                    value = str(row[i]).strip()
                    if value and value.lower() not in ("nan", "none", ""):
                        row_text.append(f"{header}: {value}")
            if row_text:
                lines.append("; ".join(row_text))

        return "\n".join(lines)

    def _chunk_from_text(self, document: ParsedDocument) -> List[Chunk]:
        """Chunk table-like text (TSV/CSV in raw text)."""
        chunks = []
        lines = document.raw_text.split("\n")

        current_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            current_lines.append(line)

            if len(current_lines) >= self.rows_per_chunk:
                text = "\n".join(current_lines)
                chunks.append(
                    Chunk(
                        text=text,
                        chunk_type=ChunkType.TABLE_BLOCK,
                        source_file=document.source_file,
                    )
                )
                current_lines = []

        # Remaining lines
        if current_lines:
            text = "\n".join(current_lines)
            chunks.append(
                Chunk(
                    text=text,
                    chunk_type=ChunkType.TABLE_BLOCK,
                    source_file=document.source_file,
                )
            )

        return chunks
