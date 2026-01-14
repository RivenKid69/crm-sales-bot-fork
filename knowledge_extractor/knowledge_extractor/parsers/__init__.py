"""Document parsers module."""

from .base import AbstractParser, ParsedDocument, ContentType
from .pdf_parser import PDFParser
from .docx_parser import DOCXParser
from .txt_parser import TXTParser
from .excel_parser import ExcelParser
from .messenger_parser import MessengerParser
from .qa_parser import QAParser

__all__ = [
    "AbstractParser",
    "ParsedDocument",
    "ContentType",
    "PDFParser",
    "DOCXParser",
    "TXTParser",
    "ExcelParser",
    "MessengerParser",
    "QAParser",
]


def get_parser_for_file(filepath: str) -> AbstractParser:
    """Get appropriate parser for file type."""
    filepath_lower = filepath.lower()

    if filepath_lower.endswith(".pdf"):
        return PDFParser()
    elif filepath_lower.endswith(".docx"):
        return DOCXParser()
    elif filepath_lower.endswith((".xlsx", ".xls", ".csv")):
        return ExcelParser()
    elif filepath_lower.endswith((".txt", ".md")):
        return TXTParser()
    else:
        # Default to text parser
        return TXTParser()
