"""
AutonomousKBProvider — direct KB access for autonomous flow.

Bypasses CategoryRouter + CascadeRetriever entirely.
Loads facts directly from KnowledgeBase.get_by_category() for the
categories defined in the current state's kb_categories field.

Zero LLM calls, zero ML overhead — just dict lookups + concatenation.

Token budget: ~10K tokens (~40K chars) per turn.
"""

import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Max characters for KB facts (~10K tokens for Qwen3 14B)
MAX_KB_CHARS = 40_000


def load_facts_for_state(
    state: str,
    flow_config,
    kb=None,
) -> Tuple[str, List[Dict[str, str]]]:
    """
    Load KB facts directly for the given state's kb_categories.

    Args:
        state: Current dialogue state (e.g. "autonomous_discovery")
        flow_config: FlowConfig with states containing kb_categories
        kb: KnowledgeBase instance (loaded from retriever if None)

    Returns:
        Tuple of (facts_text, urls_list):
        - facts_text: Concatenated facts from all matching categories, sorted
          by priority DESC, capped at MAX_KB_CHARS
        - urls_list: List of URL dicts from matching sections
    """
    # Get kb_categories from state config
    state_config = flow_config.states.get(state, {})
    kb_categories = state_config.get("kb_categories", [])

    if not kb_categories:
        logger.debug(
            "No kb_categories for state %s, returning empty",
            state,
        )
        return "", []

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
        return "", []

    # Sort by priority DESC (higher priority first)
    all_sections.sort(key=lambda s: s.priority, reverse=True)

    # Build facts text, capped at MAX_KB_CHARS
    facts_parts = []
    urls = []
    total_chars = 0

    for section in all_sections:
        section_text = f"[{section.category}/{section.topic}]\n{section.facts}\n"
        section_len = len(section_text)

        if total_chars + section_len > MAX_KB_CHARS:
            # Truncate last section if needed
            remaining = MAX_KB_CHARS - total_chars
            if remaining > 200:
                facts_parts.append(section_text[:remaining] + "...")
                if section.urls:
                    urls.extend(section.urls)
            break

        facts_parts.append(section_text)
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
            "total_chars": len(facts_text),
            "urls_count": len(urls),
        },
    )

    return facts_text, urls
