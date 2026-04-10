"""
AutonomousKBProvider — direct KB access for autonomous flow.

Bypasses CategoryRouter + CascadeRetriever entirely.
Loads facts directly from KnowledgeBase.get_by_category() for the
categories defined in the current state's kb_categories field.

Zero LLM calls, zero ML overhead — just dict lookups + concatenation.

Token budget: ~2.5K tokens (~10K chars) per turn.

Assembly policy:
- Two-pass selection.
- Pass 1 reserves one anchor section per configured category.
- Pass 2 fills remaining budget with the best global sections.
- recently_used_keys lower preference, but can no longer erase a category.
"""

import logging
import re
from typing import Dict, Iterable, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Max characters for KB facts (state backfill).
MAX_KB_CHARS = 10_000
MIN_SECTION_CHARS = 200

# Strip KB editor-only annotations before sending facts to LLM.
_KB_META_STRIP_RE = re.compile(
    r"(?m)^\s*(?:•\s*)?⚠️\s*НЕ\s+ПУТАТЬ:[^\n]*\n?",
)
_TOKEN_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё]{3,}")


def _tokenize_text(value: object) -> Set[str]:
    if value is None:
        return set()
    if not isinstance(value, str):
        value = str(value)
    return {match.group(0).lower() for match in _TOKEN_RE.finditer(value)}


def _collect_context_terms(collected_data: Optional[dict]) -> Set[str]:
    terms: Set[str] = set()
    if not isinstance(collected_data, dict):
        return terms
    for value in collected_data.values():
        if isinstance(value, str):
            terms.update(_tokenize_text(value))
        elif isinstance(value, (int, float)):
            terms.add(str(value))
    return terms


def _section_terms(section) -> Set[str]:
    terms = _tokenize_text(section.category)
    terms.update(_tokenize_text(section.topic.replace("_", " ")))
    for keyword in section.keywords or []:
        terms.update(_tokenize_text(keyword))
    return terms


def _section_key(section) -> str:
    return f"{section.category}/{section.topic}"


def _sort_key(section, *, query_terms: Set[str], context_terms: Set[str]) -> Tuple[int, int, int]:
    section_terms = _section_terms(section)
    query_overlap = len(section_terms & query_terms) if query_terms else 0
    context_overlap = len(section_terms & context_terms) if context_terms else 0
    return (query_overlap, context_overlap, section.priority)


def _rank_sections(
    sections: Iterable,
    *,
    query_terms: Set[str],
    context_terms: Set[str],
) -> List:
    return sorted(
        sections,
        key=lambda section: _sort_key(
            section,
            query_terms=query_terms,
            context_terms=context_terms,
        ),
        reverse=True,
    )


def _render_section_text(section) -> str:
    clean_facts = _KB_META_STRIP_RE.sub("", section.facts or "")
    return f"[{section.category}/{section.topic}]\n{clean_facts}\n"


def _append_section(
    section,
    *,
    budget: int,
    facts_parts: List[str],
    urls: List[Dict[str, str]],
    used_keys: List[str],
) -> int:
    if budget <= 0 or section.sensitive:
        return 0

    section_text = _render_section_text(section)
    section_key = _section_key(section)

    if len(section_text) > budget:
        if budget < MIN_SECTION_CHARS:
            return 0
        section_text = section_text[:budget].rstrip()
        if not section_text.endswith("..."):
            section_text += "..."

    facts_parts.append(section_text)
    used_keys.append(section_key)
    if section.urls:
        urls.extend(section.urls)
    return len(section_text)


def load_facts_for_state(
    state: str,
    flow_config,
    kb=None,
    recently_used_keys: Set[str] = None,
    collected_data: Optional[dict] = None,
    user_message: str = "",
    intent: str = "",
) -> Tuple[str, List[Dict[str, str]], List[str]]:
    """
    Load KB facts directly for the given state's kb_categories.

    Args:
        state: Current dialogue state (e.g. "autonomous_discovery")
        flow_config: FlowConfig with states containing kb_categories
        kb: KnowledgeBase instance (loaded from retriever if None)
        recently_used_keys: Set of "category/topic" keys used in recent turns.
            These sections are deprioritized, but category anchors still fall
            back to them when needed.
        collected_data: Optional conversation context (collected slots) used
            to boost sections with overlapping keywords.
        user_message: Current user message, used for query-aware ranking.
        intent: Current intent label, available for logging/debugging.

    Returns:
        Tuple of (facts_text, urls_list, fact_keys_used):
        - facts_text: Concatenated facts from all matching categories, built in
          two passes (category anchors first, then best remaining sections)
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
    sections_by_category: Dict[str, List] = {}
    all_sections: List = []
    for category in kb_categories:
        sections = list(kb.get_by_category(category))
        sections_by_category[category] = sections
        all_sections.extend(sections)

    if not all_sections:
        logger.warning(
            "No KB sections found for categories %s (state=%s)",
            kb_categories,
            state,
        )
        return "", [], []

    recently_used_keys = recently_used_keys or set()
    query_terms = _tokenize_text(user_message)
    context_terms = _collect_context_terms(collected_data)

    anchors: List = []
    anchor_keys: Set[str] = set()
    for category in kb_categories:
        category_sections = sections_by_category.get(category, [])
        if not category_sections:
            continue
        fresh_sections = [
            section for section in category_sections
            if _section_key(section) not in recently_used_keys
        ]
        seen_sections = [
            section for section in category_sections
            if _section_key(section) in recently_used_keys
        ]
        ranked_fresh = _rank_sections(
            fresh_sections,
            query_terms=query_terms,
            context_terms=context_terms,
        )
        ranked_seen = _rank_sections(
            seen_sections,
            query_terms=query_terms,
            context_terms=context_terms,
        )
        anchor = ranked_fresh[0] if ranked_fresh else (ranked_seen[0] if ranked_seen else None)
        if anchor is None:
            continue
        anchors.append(anchor)
        anchor_keys.add(_section_key(anchor))

    fresh = [
        section for section in all_sections
        if _section_key(section) not in recently_used_keys and _section_key(section) not in anchor_keys
    ]
    seen = [
        section for section in all_sections
        if _section_key(section) in recently_used_keys and _section_key(section) not in anchor_keys
    ]
    fresh = _rank_sections(fresh, query_terms=query_terms, context_terms=context_terms)
    seen = _rank_sections(seen, query_terms=query_terms, context_terms=context_terms)

    # Build facts text, capped at MAX_KB_CHARS
    facts_parts = []
    urls = []
    used_keys = []
    total_chars = 0

    for index, section in enumerate(anchors):
        remaining_anchors = len(anchors) - index - 1
        remaining_budget = MAX_KB_CHARS - total_chars
        reserved_tail = remaining_anchors * MIN_SECTION_CHARS
        budget_for_section = max(0, remaining_budget - reserved_tail)
        if budget_for_section <= 0:
            continue
        total_chars += _append_section(
            section,
            budget=budget_for_section,
            facts_parts=facts_parts,
            urls=urls,
            used_keys=used_keys,
        )

    for section in fresh + seen:
        remaining_budget = MAX_KB_CHARS - total_chars
        added_chars = _append_section(
            section,
            budget=remaining_budget,
            facts_parts=facts_parts,
            urls=urls,
            used_keys=used_keys,
        )
        if not added_chars:
            continue
        total_chars += added_chars

    facts_text = "\n".join(facts_parts)

    logger.info(
        "AutonomousKB loaded facts",
        extra={
            "state": state,
            "intent": intent,
            "categories": kb_categories,
            "sections_count": len(all_sections),
            "anchors_count": len(anchors),
            "used_sections": len(facts_parts),
            "fresh_sections": len(fresh),
            "seen_sections": len(seen),
            "total_chars": len(facts_text),
            "urls_count": len(urls),
            "query_terms_count": len(query_terms),
            "context_terms_count": len(context_terms),
        },
    )

    return facts_text, urls, used_keys
