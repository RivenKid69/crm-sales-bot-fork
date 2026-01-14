"""Plain text parser with encoding detection."""

import logging
import re
from pathlib import Path

from .base import AbstractParser, ContentType, ParsedDocument

logger = logging.getLogger(__name__)


class TXTParser(AbstractParser):
    """Parse plain text files with encoding detection."""

    SUPPORTED_EXTENSIONS = {".txt", ".md", ".text"}

    def supports(self, filepath: Path) -> bool:
        return filepath.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def parse(self, filepath: Path) -> ParsedDocument:
        """Parse text file with encoding detection."""
        filepath = Path(filepath)
        logger.info(f"Parsing TXT: {filepath}")

        # Detect encoding
        encoding = self._detect_encoding(filepath)
        logger.debug(f"Detected encoding: {encoding}")

        try:
            with open(filepath, "r", encoding=encoding) as f:
                raw_text = f.read()
        except UnicodeDecodeError:
            # Fallback to utf-8 with errors ignored
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                raw_text = f.read()

        raw_text = self.clean_text(raw_text)

        # Detect content type
        content_type = self._detect_content_type(raw_text)

        # Split into sections
        sections = self._split_sections(raw_text)

        # Extract Q&A pairs if applicable
        qa_pairs = []
        if content_type == ContentType.QA_PAIRS:
            qa_pairs = self._extract_qa_pairs(raw_text)

        return ParsedDocument(
            source_file=str(filepath),
            content_type=content_type,
            raw_text=raw_text,
            metadata={"encoding": encoding},
            language=self.detect_language(raw_text),
            sections=sections,
            qa_pairs=qa_pairs,
        )

    def _detect_encoding(self, filepath: Path) -> str:
        """Detect file encoding using chardet."""
        try:
            import chardet

            with open(filepath, "rb") as f:
                result = chardet.detect(f.read())
                return result.get("encoding", "utf-8") or "utf-8"
        except ImportError:
            return "utf-8"

    def _detect_content_type(self, text: str) -> ContentType:
        """Detect content type from text structure."""
        # Check for Q&A patterns
        qa_pattern = r"(?:вопрос|q|в)[:\s]*.*?(?:ответ|a|о)[:\s]*"
        if len(re.findall(qa_pattern, text, re.IGNORECASE)) > 3:
            return ContentType.QA_PAIRS

        # Check for tabular structure (TSV/CSV-like)
        lines = text.split("\n")
        tab_lines = sum(1 for line in lines if "\t" in line)
        if tab_lines > len(lines) * 0.5:
            return ContentType.TABLE

        return ContentType.PROSE

    def _split_sections(self, text: str) -> list:
        """Split text into sections by headers."""
        # Markdown headers
        sections = re.split(r"\n#{1,3}\s+", text)

        # If no markdown headers, try numbered sections
        if len(sections) <= 1:
            sections = re.split(r"\n\d+\.\s+(?=[А-ЯA-Z])", text)

        # If still no sections, split by double newlines
        if len(sections) <= 1:
            sections = re.split(r"\n\n+", text)

        return [s.strip() for s in sections if s.strip()]

    def _extract_qa_pairs(self, text: str) -> list:
        """Extract Q&A pairs from text."""
        pairs = []

        # Pattern: Q: ... A: ...
        pattern = r"(?:вопрос|q|в)[:\s]*(.+?)(?:ответ|a|о)[:\s]*(.+?)(?=(?:вопрос|q|в)[:\s]|$)"
        matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)

        for q, a in matches:
            q = q.strip()
            a = a.strip()
            if q and a:
                pairs.append((q, a))

        # Alternative: Lines ending with ? followed by answer
        if not pairs:
            lines = text.split("\n")
            i = 0
            while i < len(lines) - 1:
                line = lines[i].strip()
                if line.endswith("?"):
                    # Next non-empty line is answer
                    j = i + 1
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                    if j < len(lines):
                        answer = lines[j].strip()
                        if answer and not answer.endswith("?"):
                            pairs.append((line, answer))
                            i = j
                i += 1

        return pairs
