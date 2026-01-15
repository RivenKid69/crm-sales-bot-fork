"""Keyword generation with morphology, typos, and variations."""

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Set

from ..config import COMMON_TYPOS, KEYBOARD_NEIGHBORS_RU

logger = logging.getLogger(__name__)


@dataclass
class KeywordSet:
    """Complete keyword set for a section."""

    primary: List[str] = field(default_factory=list)
    synonyms: List[str] = field(default_factory=list)
    morphological: List[str] = field(default_factory=list)
    typos: List[str] = field(default_factory=list)
    colloquial: List[str] = field(default_factory=list)
    questions: List[str] = field(default_factory=list)
    transliterated: List[str] = field(default_factory=list)

    def to_flat_list(self, max_count: int = 50) -> List[str]:
        """Merge all keywords into flat unique list."""
        all_keywords = []
        seen = set()

        # Priority order: primary > questions > synonyms > morphological > typos > colloquial
        for source in [
            self.primary,
            self.questions,
            self.synonyms,
            self.morphological,
            self.typos,
            self.colloquial,
            self.transliterated,
        ]:
            for kw in source:
                kw_clean = kw.strip().lower()
                if kw_clean and kw_clean not in seen and len(kw_clean) >= 2:
                    all_keywords.append(kw_clean)
                    seen.add(kw_clean)

        return all_keywords[:max_count]

    def __len__(self) -> int:
        return len(self.to_flat_list())


class KeywordGenerator:
    """Generate keywords with variations."""

    def __init__(self, llm_client=None, use_morphology: bool = True):
        self.llm = llm_client
        self.use_morphology = use_morphology
        self._morph = None

        if use_morphology:
            try:
                import pymorphy3
                self._morph = pymorphy3.MorphAnalyzer()
            except ImportError:
                logger.warning("pymorphy3 not available, morphology disabled")
                self.use_morphology = False

    def generate(
        self,
        primary_keywords: List[str],
        synonyms: List[str] = None,
        question_phrases: List[str] = None,
        text_context: str = "",
    ) -> KeywordSet:
        """Generate complete keyword set from primary keywords."""
        synonyms = synonyms or []
        question_phrases = question_phrases or []

        # Start with provided keywords
        kw_set = KeywordSet(
            primary=primary_keywords,
            synonyms=synonyms,
            questions=question_phrases,
        )

        # Add morphological variations
        if self.use_morphology:
            kw_set.morphological = self._expand_morphology(primary_keywords + synonyms)

        # Add typos
        kw_set.typos = self._generate_typos(primary_keywords + synonyms)

        # Add transliterations
        kw_set.transliterated = self._transliterate(primary_keywords + synonyms)

        # Add colloquial forms (from LLM if available)
        if self.llm:
            kw_set.colloquial = self._generate_colloquial_llm(primary_keywords, text_context)

        return kw_set

    def _expand_morphology(self, keywords: List[str]) -> List[str]:
        """Expand keywords with morphological forms using pymorphy3."""
        if not self._morph:
            return []

        expanded = []
        seen = set()

        for kw in keywords:
            # Skip multi-word phrases
            if " " in kw:
                continue

            try:
                parsed = self._morph.parse(kw)
                if not parsed:
                    continue

                # Get the most likely parse
                p = parsed[0]

                # Generate all forms
                for form in p.lexeme:
                    word = form.word.lower()
                    if word not in seen and word != kw.lower():
                        expanded.append(word)
                        seen.add(word)
            except Exception as e:
                logger.debug(f"Morphology error for '{kw}': {e}")

        return expanded[:50]  # Limit

    def _generate_typos(self, keywords: List[str]) -> List[str]:
        """Generate common typos for keywords."""
        typos = []
        seen = set()

        for kw in keywords:
            kw_lower = kw.lower()

            # 1. Check predefined typos dictionary
            if kw_lower in COMMON_TYPOS:
                for typo in COMMON_TYPOS[kw_lower]:
                    if typo not in seen:
                        typos.append(typo)
                        seen.add(typo)

            # 2. Generate keyboard-based typos
            for typo in self._keyboard_typos(kw_lower):
                if typo not in seen and typo != kw_lower:
                    typos.append(typo)
                    seen.add(typo)

            # 3. Generate missing letter typos
            for typo in self._missing_letter_typos(kw_lower):
                if typo not in seen and typo != kw_lower:
                    typos.append(typo)
                    seen.add(typo)

            # 4. Generate double letter typos
            for typo in self._double_letter_typos(kw_lower):
                if typo not in seen and typo != kw_lower:
                    typos.append(typo)
                    seen.add(typo)

        return typos[:30]  # Limit

    def _keyboard_typos(self, word: str) -> List[str]:
        """Generate typos based on keyboard proximity."""
        typos = []
        if len(word) < 3:
            return typos

        for i, char in enumerate(word):
            if char in KEYBOARD_NEIGHBORS_RU:
                neighbors = KEYBOARD_NEIGHBORS_RU[char]
                for neighbor in neighbors[:2]:  # Limit neighbors
                    typo = word[:i] + neighbor + word[i + 1:]
                    typos.append(typo)

        return typos[:3]  # Return max 3

    def _missing_letter_typos(self, word: str) -> List[str]:
        """Generate typos with missing letters."""
        typos = []
        if len(word) < 4:
            return typos

        # Skip first and last letter
        for i in range(1, len(word) - 1):
            typo = word[:i] + word[i + 1:]
            typos.append(typo)

        return typos[:2]

    def _double_letter_typos(self, word: str) -> List[str]:
        """Generate typos with doubled letters."""
        typos = []
        if len(word) < 3:
            return typos

        # Common letters to double
        double_candidates = "нсткр"

        for i, char in enumerate(word):
            if char in double_candidates:
                typo = word[:i] + char + word[i:]
                typos.append(typo)

        return typos[:2]

    def _transliterate(self, keywords: List[str]) -> List[str]:
        """Convert English terms to Russian transliteration (EN -> RU only)."""
        # Only EN -> RU mapping (all output in Russian!)
        translit_map = {
            "price": "прайс",
            "free": "фри",
            "demo": "демо",
            "api": "апи",
            "app": "апп",
            "crm": "црм",
            "pro": "про",
            "lite": "лайт",
            "mini": "мини",
            "standard": "стандарт",
            "trial": "триал",
            "support": "саппорт",
            "online": "онлайн",
            "offline": "офлайн",
            "whatsapp": "вотсап",
            "telegram": "телеграм",
            "business": "бизнес",
            "enterprise": "энтерпрайз",
            "startup": "стартап",
            "tariff": "тариф",
            "integration": "интеграция",
        }

        result = []
        seen = set()

        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in translit_map:
                trans = translit_map[kw_lower]
                if trans not in seen:
                    result.append(trans)
                    seen.add(trans)

        return result

    def _generate_colloquial_llm(self, keywords: List[str], context: str) -> List[str]:
        """Generate colloquial forms using LLM."""
        if not self.llm:
            return []

        # Simple colloquial mappings (fallback)
        colloquial_map = {
            "бесплатно": ["халява", "даром", "за так", "на халяву"],
            "дорого": ["кусается", "не по карману", "дороговато"],
            "дёшево": ["недорого", "по карману", "доступно"],
            "работает": ["пашет", "фурычит"],
            "быстро": ["шустро", "мигом"],
        }

        result = []
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in colloquial_map:
                result.extend(colloquial_map[kw_lower])

        return result[:10]


def merge_keyword_sets(*sets: KeywordSet) -> KeywordSet:
    """Merge multiple keyword sets into one."""
    merged = KeywordSet()

    for kw_set in sets:
        merged.primary.extend(kw_set.primary)
        merged.synonyms.extend(kw_set.synonyms)
        merged.morphological.extend(kw_set.morphological)
        merged.typos.extend(kw_set.typos)
        merged.colloquial.extend(kw_set.colloquial)
        merged.questions.extend(kw_set.questions)
        merged.transliterated.extend(kw_set.transliterated)

    # Deduplicate
    merged.primary = list(dict.fromkeys(merged.primary))
    merged.synonyms = list(dict.fromkeys(merged.synonyms))
    merged.morphological = list(dict.fromkeys(merged.morphological))
    merged.typos = list(dict.fromkeys(merged.typos))
    merged.colloquial = list(dict.fromkeys(merged.colloquial))
    merged.questions = list(dict.fromkeys(merged.questions))
    merged.transliterated = list(dict.fromkeys(merged.transliterated))

    return merged
