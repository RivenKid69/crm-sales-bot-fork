"""Loader for isolated pain-point knowledge base."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List

import yaml

from src.logger import logger

from .base import KnowledgeBase, KnowledgeSection


PAIN_DIR = Path(__file__).resolve().parent.parent.parent / "БД по болям"

PAIN_FILE_TO_CATEGORY: Dict[str, str] = {
    "kassa.yaml": "pain_kassa",
    "equipmentwipon.yaml": "pain_equipment",
    "productswipon.yaml": "pain_products",
    "SNR.yaml": "pain_snr",
    "wiponconsulting.yaml": "pain_consulting",
}


def _normalize_keywords(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    return [str(value)]


def _extract_records(raw: object) -> Iterable[dict]:
    """Support both legacy list format and {'sections': [...]} format."""
    if isinstance(raw, list):
        return (item for item in raw if isinstance(item, dict))

    if isinstance(raw, dict):
        sections = raw.get("sections")
        if isinstance(sections, list):
            return (item for item in sections if isinstance(item, dict))

    return ()


def load_pain_knowledge_base() -> KnowledgeBase:
    """Загружает БД по болям как отдельную KnowledgeBase."""
    sections: List[KnowledgeSection] = []
    seen_topics = set()

    for filename, category in PAIN_FILE_TO_CATEGORY.items():
        filepath = PAIN_DIR / filename
        if not filepath.exists():
            logger.warning(
                "Pain KB category source not found",
                category=category,
                filename=filename,
                pain_dir=str(PAIN_DIR),
            )
            continue

        raw = yaml.safe_load(filepath.read_text(encoding="utf-8"))
        if not raw:
            continue

        records = list(_extract_records(raw))

        for item in records:
            topic = str(item.get("topic", "")).strip()
            if not topic:
                continue
            # Prefer first source in priority order when duplicate topics exist.
            if topic in seen_topics:
                continue
            seen_topics.add(topic)

            sections.append(
                KnowledgeSection(
                    category=category,
                    topic=topic,
                    keywords=_normalize_keywords(item.get("keywords", [])),
                    facts=str(item.get("facts", "")),
                    priority=int(item.get("priority", 5)),
                )
            )

    return KnowledgeBase(
        company_name="Wipon",
        company_description="БД решений по болям клиентов",
        sections=sections,
    )
