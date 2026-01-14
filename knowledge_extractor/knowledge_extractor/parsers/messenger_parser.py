"""Messenger export parser (WhatsApp, Telegram)."""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

from .base import AbstractParser, ContentType, ParsedDocument

logger = logging.getLogger(__name__)


class MessengerParser(AbstractParser):
    """Parse WhatsApp and Telegram chat exports."""

    SUPPORTED_EXTENSIONS = {".txt"}

    def __init__(self, format_hint: str = "auto"):
        """
        Initialize parser.

        Args:
            format_hint: "whatsapp", "telegram", or "auto" for detection
        """
        self.format_hint = format_hint

    def supports(self, filepath: Path) -> bool:
        # Supports .txt, but needs format check
        return filepath.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def parse(self, filepath: Path) -> ParsedDocument:
        """Parse messenger export."""
        filepath = Path(filepath)
        logger.info(f"Parsing messenger export: {filepath}")

        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            raw_content = f.read()

        # Detect format
        format_type = self._detect_format(raw_content)
        logger.debug(f"Detected format: {format_type}")

        # Parse messages
        messages = self._parse_messages(raw_content, format_type)
        logger.info(f"Parsed {len(messages)} messages")

        # Group into conversation threads
        threads = self._group_threads(messages)

        # Extract Q&A patterns (question followed by answer)
        qa_pairs = self._extract_qa_from_messages(messages)

        # Build text representation
        text_parts = []
        for i, thread in enumerate(threads):
            text_parts.append(f"--- Тема {i + 1} ---")
            for msg in thread:
                text_parts.append(f"[{msg['sender']}]: {msg['text']}")
            text_parts.append("")

        raw_text = self.clean_text("\n".join(text_parts))

        return ParsedDocument(
            source_file=str(filepath),
            content_type=ContentType.CHAT,
            raw_text=raw_text,
            metadata={
                "format": format_type,
                "message_count": len(messages),
                "thread_count": len(threads),
            },
            language=self.detect_language(raw_text),
            sections=["\n".join(f"[{m['sender']}]: {m['text']}" for m in t) for t in threads],
            qa_pairs=qa_pairs,
        )

    def _detect_format(self, content: str) -> str:
        """Detect messenger format from content."""
        if self.format_hint != "auto":
            return self.format_hint

        # WhatsApp pattern: "DD/MM/YYYY, HH:MM - Name: Message"
        # or "[DD.MM.YYYY, HH:MM:SS] Name: Message"
        whatsapp_pattern = r"\d{1,2}[/.]\d{1,2}[/.]\d{2,4},?\s*\d{1,2}:\d{2}"
        if re.search(whatsapp_pattern, content[:1000]):
            return "whatsapp"

        # Telegram pattern: various formats
        telegram_pattern = r"\[\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}:\d{2}\]"
        if re.search(telegram_pattern, content[:1000]):
            return "telegram"

        return "generic"

    def _parse_messages(self, content: str, format_type: str) -> List[dict]:
        """Parse messages from content."""
        messages = []

        if format_type == "whatsapp":
            # WhatsApp format: "DD/MM/YYYY, HH:MM - Sender: Message"
            pattern = r"(\d{1,2}[/.]\d{1,2}[/.]\d{2,4}),?\s*(\d{1,2}:\d{2})\s*-\s*([^:]+):\s*(.+?)(?=\d{1,2}[/.]\d{1,2}[/.]\d{2,4}|$)"
            matches = re.findall(pattern, content, re.DOTALL)
            for date, time, sender, text in matches:
                messages.append({
                    "date": date,
                    "time": time,
                    "sender": sender.strip(),
                    "text": text.strip(),
                })

        elif format_type == "telegram":
            # Telegram JSON export or text export
            pattern = r"\[(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2}:\d{2})\]\s*([^:]+):\s*(.+?)(?=\[|$)"
            matches = re.findall(pattern, content, re.DOTALL)
            for date, time, sender, text in matches:
                messages.append({
                    "date": date,
                    "time": time,
                    "sender": sender.strip(),
                    "text": text.strip(),
                })

        else:
            # Generic: split by lines and guess
            lines = content.split("\n")
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                # Try to extract sender
                if ":" in line:
                    parts = line.split(":", 1)
                    sender = parts[0].strip()[-50:]  # Limit sender length
                    text = parts[1].strip() if len(parts) > 1 else ""
                    if text:
                        messages.append({
                            "sender": sender,
                            "text": text,
                        })

        return messages

    def _group_threads(
        self,
        messages: List[dict],
        gap_minutes: int = 60,
    ) -> List[List[dict]]:
        """Group messages into conversation threads by time gaps."""
        if not messages:
            return []

        threads = []
        current_thread = [messages[0]]

        for msg in messages[1:]:
            # Simple grouping: start new thread if sender pattern repeats
            # Or if no timestamps, group by 10-20 messages
            if len(current_thread) >= 20:
                threads.append(current_thread)
                current_thread = []

            current_thread.append(msg)

        if current_thread:
            threads.append(current_thread)

        return threads

    def _extract_qa_from_messages(self, messages: List[dict]) -> List[Tuple[str, str]]:
        """Extract Q&A pairs from message flow."""
        qa_pairs = []

        for i, msg in enumerate(messages[:-1]):
            text = msg.get("text", "")
            # If message ends with ? and next message is an answer
            if text.strip().endswith("?"):
                next_msg = messages[i + 1]
                next_text = next_msg.get("text", "")
                # Answer should not be a question
                if next_text and not next_text.strip().endswith("?"):
                    qa_pairs.append((text.strip(), next_text.strip()))

        return qa_pairs
