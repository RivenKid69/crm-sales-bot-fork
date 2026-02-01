"""
KB Question Pool for E2E simulation.

Provides fact-grounded client questions loaded from pre-generated JSON.
Questions are organized by persona affinity for realistic dialogue simulation.

Usage:
    from src.simulator.kb_questions import load_kb_question_pool

    pool = load_kb_question_pool()
    if pool:
        q = pool.get_starter("technical")
        followup = pool.get_followup("technical", exclude_topics={"wipon_kassa"})
"""

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set


@dataclass
class KBQuestion:
    """A single KB-grounded client question."""
    text: str
    category: str
    source_topic: str
    priority: int


# Persona -> category affinity weights
# Higher weight = more likely to pick questions from that category
PERSONA_CATEGORY_AFFINITY: Dict[str, Dict[str, float]] = {
    "happy_path": {
        "products": 1.0, "features": 0.8, "support": 0.6, "pricing": 0.5,
        "integrations": 0.4, "tis": 0.3, "mobile": 0.3, "analytics": 0.2,
    },
    "price_sensitive": {
        "pricing": 1.0, "promotions": 0.9, "products": 0.5,
        "competitors": 0.4, "tis": 0.3,
    },
    "technical": {
        "integrations": 1.0, "features": 0.9, "stability": 0.8,
        "analytics": 0.7, "equipment": 0.6, "fiscal": 0.5, "mobile": 0.4,
    },
    "competitor_user": {
        "competitors": 1.0, "features": 0.8, "products": 0.7,
        "integrations": 0.6, "pricing": 0.4,
    },
    "skeptic": {
        "stability": 1.0, "support": 0.8, "competitors": 0.7,
        "faq": 0.5, "features": 0.4,
    },
    "busy": {
        "pricing": 1.0, "products": 0.7, "features": 0.3,
    },
    "aggressive": {
        "pricing": 1.0, "products": 0.6, "support": 0.4,
    },
    "tire_kicker": {
        "products": 0.8, "faq": 0.7, "pricing": 0.4, "features": 0.3,
    },
}


class KBQuestionPool:
    """Pool of KB-grounded questions organized by persona affinity.

    Immutable after __init__. Methods use random.choice() from the
    random module (thread-safe under GIL).
    """

    def __init__(self, json_path: str):
        """Load JSON and build per-persona pools sorted by priority.

        Args:
            json_path: Path to kb_questions.json
        """
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Parse all questions
        self._all_questions: List[KBQuestion] = []
        for q_data in data.get("questions", []):
            self._all_questions.append(KBQuestion(
                text=q_data["text"],
                category=q_data["category"],
                source_topic=q_data["source_topic"],
                priority=q_data.get("priority", 5),
            ))

        # Build per-category index
        self._by_category: Dict[str, List[KBQuestion]] = {}
        for q in self._all_questions:
            self._by_category.setdefault(q.category, []).append(q)

        # Build per-persona pools (sorted by affinity-weighted priority)
        self._persona_pools: Dict[str, List[KBQuestion]] = {}
        for persona_key, affinities in PERSONA_CATEGORY_AFFINITY.items():
            pool: List[KBQuestion] = []
            for q in self._all_questions:
                affinity = affinities.get(q.category, 0.1)  # default low affinity
                if affinity > 0:
                    pool.append(q)
            # Sort by affinity * priority (descending)
            pool.sort(
                key=lambda q: affinities.get(q.category, 0.1) * q.priority,
                reverse=True,
            )
            self._persona_pools[persona_key] = pool

    def get_starter(self, persona_key: str) -> Optional[KBQuestion]:
        """Pick a random question from persona pool.

        Args:
            persona_key: Persona identifier (e.g. "technical", "busy")

        Returns:
            KBQuestion or None if pool is empty
        """
        pool = self._persona_pools.get(persona_key, self._all_questions)
        if not pool:
            return None
        return random.choice(pool)

    def get_followup(self, persona_key: str, exclude_topics: Set[str]) -> Optional[KBQuestion]:
        """Pick a random question excluding already-asked topics.

        Args:
            persona_key: Persona identifier
            exclude_topics: Set of topic strings to exclude

        Returns:
            KBQuestion or None if no eligible questions remain
        """
        pool = self._persona_pools.get(persona_key, self._all_questions)
        filtered = [q for q in pool if q.source_topic not in exclude_topics]
        if not filtered:
            return None
        return random.choice(filtered)

    def get_random(self, category: Optional[str] = None) -> Optional[KBQuestion]:
        """Get a random question, optionally filtered by category.

        Args:
            category: Category filter (e.g. "pricing")

        Returns:
            KBQuestion or None
        """
        if category:
            pool = self._by_category.get(category, [])
        else:
            pool = self._all_questions
        if not pool:
            return None
        return random.choice(pool)

    @property
    def total_questions(self) -> int:
        """Total number of questions in the pool."""
        return len(self._all_questions)

    @property
    def categories(self) -> List[str]:
        """List of available categories."""
        return sorted(self._by_category.keys())


# Module-level cache
_pool_cache: Optional[KBQuestionPool] = None


def load_kb_question_pool() -> Optional[KBQuestionPool]:
    """Load KB question pool from default path.

    Returns None with warning if file not found (batch script not run yet).
    Cached after first successful load.
    """
    global _pool_cache
    if _pool_cache is not None:
        return _pool_cache

    json_path = Path(__file__).parent / "data" / "kb_questions.json"
    if not json_path.exists():
        print("WARNING: kb_questions.json not found. Run: python scripts/generate_kb_questions.py")
        return None

    _pool_cache = KBQuestionPool(str(json_path))
    return _pool_cache


def reset_pool_cache():
    """Reset the module-level cache. Useful for testing."""
    global _pool_cache
    _pool_cache = None
