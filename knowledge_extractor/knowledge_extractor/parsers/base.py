"""Base parser classes."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class ContentType(Enum):
    """Type of document content."""

    PROSE = "prose"  # Regular text (PDF, DOCX)
    QA_PAIRS = "qa_pairs"  # Question-answer pairs
    TABLE = "table"  # Tabular data
    CHAT = "chat"  # Messenger exports
    MIXED = "mixed"  # Mixed content


@dataclass
class ParsedDocument:
    """Parsed document representation."""

    source_file: str
    content_type: ContentType
    raw_text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    language: str = "ru"

    # For structured content
    sections: List[str] = field(default_factory=list)  # Split by headers
    tables: List[List[List[str]]] = field(default_factory=list)  # Table data
    qa_pairs: List[tuple] = field(default_factory=list)  # (question, answer) pairs

    def __len__(self) -> int:
        return len(self.raw_text)

    @property
    def is_empty(self) -> bool:
        return len(self.raw_text.strip()) == 0


class AbstractParser(ABC):
    """Base parser interface."""

    @abstractmethod
    def parse(self, filepath: Path) -> ParsedDocument:
        """Parse document and return ParsedDocument."""
        pass

    @abstractmethod
    def supports(self, filepath: Path) -> bool:
        """Check if parser supports this file type."""
        pass

    def detect_language(self, text: str) -> str:
        """Simple language detection (ru/kk/en)."""
        # Count Cyrillic vs Latin characters
        cyrillic = sum(1 for c in text if "\u0400" <= c <= "\u04ff")
        latin = sum(1 for c in text if "a" <= c.lower() <= "z")

        if cyrillic > latin:
            # Check for Kazakh-specific characters
            kazakh_chars = sum(
                1 for c in text if c in "әғқңөұүіһӘҒҚҢӨҰҮІҺ"
            )
            if kazakh_chars > len(text) * 0.01:  # More than 1%
                return "kk"
            return "ru"
        return "en"

    def clean_text(self, text: str) -> str:
        """Clean extracted text."""
        import re

        # Remove excessive whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)

        # Remove control characters except newlines
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

        return text.strip()
