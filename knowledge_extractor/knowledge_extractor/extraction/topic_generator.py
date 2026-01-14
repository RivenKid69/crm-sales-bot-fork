"""Topic ID generation."""

import re
import unicodedata
from typing import Set


class TopicGenerator:
    """Generate unique topic IDs in snake_case format."""

    def __init__(self):
        self._used_topics: Set[str] = set()
        self._counter = 0

    def generate(self, text_hint: str, category: str = "") -> str:
        """Generate unique topic ID from text hint."""
        # Transliterate and clean
        base = self._to_snake_case(text_hint)

        # Add category prefix if short
        if len(base) < 5 and category:
            base = f"{category}_{base}"

        # Ensure minimum length
        if len(base) < 3:
            base = f"section_{base}"

        # Make unique
        topic = self._make_unique(base)
        self._used_topics.add(topic)

        return topic

    def _to_snake_case(self, text: str) -> str:
        """Convert text to snake_case ASCII."""
        # Transliterate Cyrillic to Latin
        text = self._transliterate_cyrillic(text)

        # Remove non-alphanumeric (except spaces)
        text = re.sub(r"[^\w\s]", "", text)

        # Replace spaces with underscores
        text = re.sub(r"\s+", "_", text.strip())

        # Convert to lowercase
        text = text.lower()

        # Remove consecutive underscores
        text = re.sub(r"_+", "_", text)

        # Remove leading/trailing underscores
        text = text.strip("_")

        # Limit length
        if len(text) > 50:
            text = text[:50].rsplit("_", 1)[0]

        return text

    def _transliterate_cyrillic(self, text: str) -> str:
        """Transliterate Cyrillic to Latin."""
        translit_map = {
            "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
            "ё": "yo", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k",
            "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
            "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
            "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "",
            "э": "e", "ю": "yu", "я": "ya",
            # Kazakh specific
            "ә": "a", "ғ": "gh", "қ": "q", "ң": "ng", "ө": "o",
            "ұ": "u", "ү": "u", "і": "i", "һ": "h",
        }

        result = []
        for char in text.lower():
            if char in translit_map:
                result.append(translit_map[char])
            elif char.isascii():
                result.append(char)
            else:
                # Try to normalize
                normalized = unicodedata.normalize("NFKD", char)
                ascii_char = normalized.encode("ascii", "ignore").decode("ascii")
                result.append(ascii_char)

        return "".join(result)

    def _make_unique(self, base: str) -> str:
        """Make topic unique by adding suffix if needed."""
        if base not in self._used_topics:
            return base

        # Add numeric suffix
        self._counter += 1
        candidate = f"{base}_{self._counter}"

        while candidate in self._used_topics:
            self._counter += 1
            candidate = f"{base}_{self._counter}"

        return candidate

    def register_existing(self, topics: Set[str]):
        """Register existing topics to avoid collisions."""
        self._used_topics.update(topics)

    def reset(self):
        """Reset generator state."""
        self._used_topics.clear()
        self._counter = 0
