"""PDF document parser using PyMuPDF."""

import logging
from pathlib import Path
from typing import List

from .base import AbstractParser, ContentType, ParsedDocument

logger = logging.getLogger(__name__)


class PDFParser(AbstractParser):
    """Parse PDF documents using PyMuPDF (fitz)."""

    SUPPORTED_EXTENSIONS = {".pdf"}

    def supports(self, filepath: Path) -> bool:
        return filepath.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def parse(self, filepath: Path) -> ParsedDocument:
        """Parse PDF and extract text."""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError("PyMuPDF not installed. Run: pip install pymupdf")

        filepath = Path(filepath)
        logger.info(f"Parsing PDF: {filepath}")

        text_parts = []
        sections = []
        metadata = {}

        try:
            doc = fitz.open(filepath)

            # Extract metadata
            metadata = {
                "title": doc.metadata.get("title", ""),
                "author": doc.metadata.get("author", ""),
                "page_count": len(doc),
            }

            current_section = []

            for page_num, page in enumerate(doc):
                # Extract text
                page_text = page.get_text("text")
                text_parts.append(page_text)

                # Try to detect section breaks (headers)
                blocks = page.get_text("dict")["blocks"]
                for block in blocks:
                    if "lines" in block:
                        for line in block["lines"]:
                            for span in line["spans"]:
                                # Large font = likely header
                                if span["size"] > 14:
                                    if current_section:
                                        sections.append("\n".join(current_section))
                                        current_section = []
                                current_section.append(span["text"])

            # Add last section
            if current_section:
                sections.append("\n".join(current_section))

            doc.close()

        except Exception as e:
            logger.error(f"Error parsing PDF {filepath}: {e}")
            raise

        raw_text = self.clean_text("\n".join(text_parts))

        return ParsedDocument(
            source_file=str(filepath),
            content_type=ContentType.PROSE,
            raw_text=raw_text,
            metadata=metadata,
            language=self.detect_language(raw_text),
            sections=sections if sections else [raw_text],
        )

    def extract_tables(self, filepath: Path) -> List[List[List[str]]]:
        """Extract tables from PDF (if any)."""
        try:
            import fitz
        except ImportError:
            return []

        tables = []

        try:
            doc = fitz.open(filepath)
            for page in doc:
                # PyMuPDF table extraction
                page_tables = page.find_tables()
                for table in page_tables:
                    table_data = table.extract()
                    if table_data:
                        tables.append(table_data)
            doc.close()
        except Exception as e:
            logger.warning(f"Table extraction failed: {e}")

        return tables
