"""Q&A pairs parser for structured Q&A files."""

import csv
import json
import logging
from pathlib import Path
from typing import List, Tuple

from .base import AbstractParser, ContentType, ParsedDocument

logger = logging.getLogger(__name__)


class QAParser(AbstractParser):
    """Parse Q&A files in various formats (TSV, CSV, JSON)."""

    SUPPORTED_EXTENSIONS = {".tsv", ".csv", ".json", ".jsonl"}

    def supports(self, filepath: Path) -> bool:
        return filepath.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def parse(self, filepath: Path) -> ParsedDocument:
        """Parse Q&A file."""
        filepath = Path(filepath)
        logger.info(f"Parsing Q&A file: {filepath}")

        suffix = filepath.suffix.lower()

        if suffix == ".json":
            qa_pairs = self._parse_json(filepath)
        elif suffix == ".jsonl":
            qa_pairs = self._parse_jsonl(filepath)
        elif suffix == ".tsv":
            qa_pairs = self._parse_tsv(filepath)
        else:  # csv
            qa_pairs = self._parse_csv(filepath)

        logger.info(f"Extracted {len(qa_pairs)} Q&A pairs")

        # Build text representation
        text_parts = []
        for q, a in qa_pairs:
            text_parts.append(f"Вопрос: {q}")
            text_parts.append(f"Ответ: {a}")
            text_parts.append("")

        raw_text = self.clean_text("\n".join(text_parts))

        return ParsedDocument(
            source_file=str(filepath),
            content_type=ContentType.QA_PAIRS,
            raw_text=raw_text,
            metadata={"qa_count": len(qa_pairs)},
            language=self.detect_language(raw_text),
            qa_pairs=qa_pairs,
        )

    def _parse_json(self, filepath: Path) -> List[Tuple[str, str]]:
        """Parse JSON file with Q&A pairs."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        pairs = []

        # Handle various JSON structures
        if isinstance(data, list):
            for item in data:
                q, a = self._extract_qa_from_dict(item)
                if q and a:
                    pairs.append((q, a))
        elif isinstance(data, dict):
            # Single Q&A or nested structure
            if "questions" in data or "qa" in data or "items" in data:
                items = data.get("questions") or data.get("qa") or data.get("items") or []
                for item in items:
                    q, a = self._extract_qa_from_dict(item)
                    if q and a:
                        pairs.append((q, a))
            else:
                q, a = self._extract_qa_from_dict(data)
                if q and a:
                    pairs.append((q, a))

        return pairs

    def _parse_jsonl(self, filepath: Path) -> List[Tuple[str, str]]:
        """Parse JSON Lines file."""
        pairs = []
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    q, a = self._extract_qa_from_dict(item)
                    if q and a:
                        pairs.append((q, a))
                except json.JSONDecodeError:
                    continue
        return pairs

    def _parse_tsv(self, filepath: Path) -> List[Tuple[str, str]]:
        """Parse TSV file."""
        pairs = []
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="\t")
            header = next(reader, None)

            q_idx, a_idx = self._find_qa_columns_idx(header)

            for row in reader:
                if len(row) >= 2:
                    q = row[q_idx].strip() if q_idx < len(row) else ""
                    a = row[a_idx].strip() if a_idx < len(row) else ""
                    if q and a:
                        pairs.append((q, a))

        return pairs

    def _parse_csv(self, filepath: Path) -> List[Tuple[str, str]]:
        """Parse CSV file."""
        pairs = []
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, None)

            q_idx, a_idx = self._find_qa_columns_idx(header)

            for row in reader:
                if len(row) >= 2:
                    q = row[q_idx].strip() if q_idx < len(row) else ""
                    a = row[a_idx].strip() if a_idx < len(row) else ""
                    if q and a:
                        pairs.append((q, a))

        return pairs

    def _extract_qa_from_dict(self, item: dict) -> Tuple[str, str]:
        """Extract Q&A from dictionary with various key names."""
        # Question keys
        q_keys = ["question", "q", "вопрос", "query", "input", "prompt"]
        # Answer keys
        a_keys = ["answer", "a", "ответ", "response", "output", "fact", "факт"]

        q = ""
        a = ""

        for key in q_keys:
            if key in item:
                q = str(item[key]).strip()
                break
            # Case-insensitive
            for k in item.keys():
                if k.lower() == key:
                    q = str(item[k]).strip()
                    break
            if q:
                break

        for key in a_keys:
            if key in item:
                a = str(item[key]).strip()
                break
            for k in item.keys():
                if k.lower() == key:
                    a = str(item[k]).strip()
                    break
            if a:
                break

        return q, a

    def _find_qa_columns_idx(self, header: List[str]) -> Tuple[int, int]:
        """Find Q&A column indices in header."""
        if not header:
            return 0, 1

        header_lower = [h.lower() for h in header]

        q_idx = 0
        a_idx = 1

        q_patterns = ["вопрос", "question", "q", "query", "input"]
        a_patterns = ["ответ", "answer", "a", "response", "output", "fact"]

        for i, h in enumerate(header_lower):
            for p in q_patterns:
                if p in h:
                    q_idx = i
                    break

        for i, h in enumerate(header_lower):
            for p in a_patterns:
                if p in h:
                    a_idx = i
                    break

        return q_idx, a_idx
