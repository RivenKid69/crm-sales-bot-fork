"""
AutonomousKBProvider — direct KB access for autonomous flow.

Bypasses CategoryRouter + CascadeRetriever entirely.
Loads facts directly from KnowledgeBase.get_by_category() for the
categories defined in the current state's kb_categories field.

Zero LLM calls, zero ML overhead — just dict lookups + concatenation.

Token budget: ~10K tokens (~40K chars) per turn.

Fact rotation: accepts recently_used_keys to deprioritize sections that
were already shown in recent turns. Fresh sections appear first in the
token window, making it structurally unlikely the LLM repeats the same
talking points.
"""

import logging
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Max characters for KB facts (~10K tokens for Qwen3 14B)
MAX_KB_CHARS = 40_000


def load_facts_for_state(
    state: str,
    flow_config,
    kb=None,
    recently_used_keys: Set[str] = None,
) -> Tuple[str, List[Dict[str, str]], List[str]]:
    """
    Load KB facts directly for the given state's kb_categories.

    Args:
        state: Current dialogue state (e.g. "autonomous_discovery")
        flow_config: FlowConfig with states containing kb_categories
        kb: KnowledgeBase instance (loaded from retriever if None)
        recently_used_keys: Set of "category/topic" keys used in recent turns.
            These sections are deprioritized (moved after fresh sections).

    Returns:
        Tuple of (facts_text, urls_list, fact_keys_used):
        - facts_text: Concatenated facts from all matching categories, sorted
          by priority DESC with fresh sections first, capped at MAX_KB_CHARS
        - urls_list: List of URL dicts from matching sections
        - fact_keys_used: List of "category/topic" keys actually included
    """
    # Get kb_categories from state config
    state_config = flow_config.states.get(state, {})
    kb_categories = state_config.get("kb_categories", [])

    if not kb_categories:
        logger.debug(
            "No kb_categories for state %s, returning empty",
            state,
        )
        return "", [], []

    # Lazy-load KB if not provided
    if kb is None:
        from src.knowledge.retriever import get_retriever
        retriever = get_retriever()
        kb = retriever.kb

    # Collect all sections from requested categories
    all_sections = []
    for category in kb_categories:
        sections = kb.get_by_category(category)
        all_sections.extend(sections)

    if not all_sections:
        logger.warning(
            "No KB sections found for categories %s (state=%s)",
            kb_categories,
            state,
        )
        return "", [], []

    # Fact rotation: split into fresh and recently-seen sections
    recently_used_keys = recently_used_keys or set()

    fresh = [s for s in all_sections if f"{s.category}/{s.topic}" not in recently_used_keys]
    seen = [s for s in all_sections if f"{s.category}/{s.topic}" in recently_used_keys]

    # Sort each group by priority DESC (higher priority first)
    fresh.sort(key=lambda s: s.priority, reverse=True)
    seen.sort(key=lambda s: s.priority, reverse=True)

    # Fresh content appears first in token window
    all_sections = fresh + seen

    # Build facts text, capped at MAX_KB_CHARS
    facts_parts = []
    urls = []
    used_keys = []
    total_chars = 0

    for section in all_sections:
        section_text = f"[{section.category}/{section.topic}]\n{section.facts}\n"
        section_len = len(section_text)

        if total_chars + section_len > MAX_KB_CHARS:
            # Truncate last section if needed
            remaining = MAX_KB_CHARS - total_chars
            if remaining > 200:
                facts_parts.append(section_text[:remaining] + "...")
                used_keys.append(f"{section.category}/{section.topic}")
                if section.urls:
                    urls.extend(section.urls)
            break

        facts_parts.append(section_text)
        used_keys.append(f"{section.category}/{section.topic}")
        total_chars += section_len

        if section.urls:
            urls.extend(section.urls)

    facts_text = "\n".join(facts_parts)

    logger.info(
        "AutonomousKB loaded facts",
        extra={
            "state": state,
            "categories": kb_categories,
            "sections_count": len(all_sections),
            "used_sections": len(facts_parts),
            "fresh_sections": len(fresh),
            "seen_sections": len(seen),
            "total_chars": len(facts_text),
            "urls_count": len(urls),
        },
    )

    return facts_text, urls, used_keys
