"""Route sections to categories."""

import logging
from collections import defaultdict
from typing import Dict, List, Optional

from ..config import CATEGORY_FILES, CATEGORY_KEYWORDS
from ..extraction.schemas import ExtractedSection

logger = logging.getLogger(__name__)


class CategoryRouter:
    """Route sections to category files."""

    def __init__(self, llm_client=None):
        self.llm = llm_client
        self._keyword_index = self._build_keyword_index()

    def _build_keyword_index(self) -> Dict[str, str]:
        """Build keyword to category index."""
        index = {}
        for category, keywords in CATEGORY_KEYWORDS.items():
            for kw in keywords:
                index[kw.lower()] = category
        return index

    def route(self, section: ExtractedSection) -> str:
        """Determine category for section."""
        # 1. If category already set, use it
        if section.category:
            return section.category

        # 2. Analyze keywords
        category_scores = defaultdict(int)
        for kw in section.keywords:
            kw_lower = kw.lower()
            if kw_lower in self._keyword_index:
                category_scores[self._keyword_index[kw_lower]] += 1

            # Partial match
            for index_kw, cat in self._keyword_index.items():
                if index_kw in kw_lower or kw_lower in index_kw:
                    category_scores[cat] += 0.5

        if category_scores:
            return max(category_scores, key=category_scores.get)

        # 3. Analyze facts text
        facts_lower = section.facts.lower()
        for category, keywords in CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw in facts_lower:
                    category_scores[category] += 1

        if category_scores:
            return max(category_scores, key=category_scores.get)

        # 4. Default to faq
        return "faq"

    def distribute(
        self,
        sections: List[ExtractedSection],
    ) -> Dict[str, List[ExtractedSection]]:
        """Distribute sections to category files."""
        distribution = defaultdict(list)

        for section in sections:
            category = section.category or self.route(section)
            filename = CATEGORY_FILES.get(category, f"{category}.yaml")
            distribution[filename].append(section)

        # Log distribution
        for filename, sects in distribution.items():
            logger.info(f"Category {filename}: {len(sects)} sections")

        return dict(distribution)

    def get_category_stats(
        self,
        sections: List[ExtractedSection],
    ) -> Dict[str, int]:
        """Get section count by category."""
        stats = defaultdict(int)
        for section in sections:
            stats[section.category] += 1
        return dict(stats)
