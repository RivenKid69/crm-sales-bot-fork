"""Excel/CSV parser using pandas and openpyxl."""

import logging
from pathlib import Path
from typing import List

from .base import AbstractParser, ContentType, ParsedDocument

logger = logging.getLogger(__name__)


class ExcelParser(AbstractParser):
    """Parse Excel and CSV files."""

    SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv"}

    def supports(self, filepath: Path) -> bool:
        return filepath.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def parse(self, filepath: Path) -> ParsedDocument:
        """Parse Excel/CSV file."""
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pandas not installed. Run: pip install pandas openpyxl")

        filepath = Path(filepath)
        logger.info(f"Parsing Excel/CSV: {filepath}")

        tables = []
        text_parts = []
        qa_pairs = []

        try:
            # Read file
            if filepath.suffix.lower() == ".csv":
                df = pd.read_csv(filepath, encoding="utf-8")
            else:
                df = pd.read_excel(filepath)

            # Convert to table data
            headers = list(df.columns)
            table_data = [headers]
            for _, row in df.iterrows():
                table_data.append([str(v) for v in row.values])
            tables.append(table_data)

            # Generate text representation
            text_parts.append(f"Таблица: {filepath.name}")
            text_parts.append(f"Столбцы: {', '.join(headers)}")
            text_parts.append(f"Строк: {len(df)}")
            text_parts.append("")

            # Check if this is Q&A format
            q_col, a_col = self._find_qa_columns(df)
            if q_col and a_col:
                for _, row in df.iterrows():
                    q = str(row[q_col]).strip()
                    a = str(row[a_col]).strip()
                    if q and a and q != "nan" and a != "nan":
                        qa_pairs.append((q, a))
                        text_parts.append(f"В: {q}")
                        text_parts.append(f"О: {a}")
                        text_parts.append("")
            else:
                # Convert each row to text
                for _, row in df.iterrows():
                    row_text = []
                    for col, val in row.items():
                        val_str = str(val).strip()
                        if val_str and val_str != "nan":
                            row_text.append(f"{col}: {val_str}")
                    if row_text:
                        text_parts.append("; ".join(row_text))

        except Exception as e:
            logger.error(f"Error parsing {filepath}: {e}")
            raise

        raw_text = self.clean_text("\n".join(text_parts))

        content_type = ContentType.QA_PAIRS if qa_pairs else ContentType.TABLE

        return ParsedDocument(
            source_file=str(filepath),
            content_type=content_type,
            raw_text=raw_text,
            metadata={
                "columns": headers if tables else [],
                "row_count": len(df) if "df" in locals() else 0,
            },
            language=self.detect_language(raw_text),
            tables=tables,
            qa_pairs=qa_pairs,
        )

    def _find_qa_columns(self, df) -> tuple:
        """Find question and answer columns in DataFrame."""
        columns_lower = {col.lower(): col for col in df.columns}

        # Question column patterns
        q_patterns = ["вопрос", "question", "q", "запрос", "query"]
        # Answer column patterns
        a_patterns = ["ответ", "answer", "a", "response", "факт", "fact"]

        q_col = None
        a_col = None

        for pattern in q_patterns:
            for col_lower, col in columns_lower.items():
                if pattern in col_lower:
                    q_col = col
                    break
            if q_col:
                break

        for pattern in a_patterns:
            for col_lower, col in columns_lower.items():
                if pattern in col_lower:
                    a_col = col
                    break
            if a_col:
                break

        return q_col, a_col
