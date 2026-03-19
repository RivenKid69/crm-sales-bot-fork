"""Shared text pool for unknown / KB-empty fallback replies."""

from __future__ import annotations

import random
import re
from typing import Optional


UNKNOWN_KB_FALLBACK_VARIANTS = (
    "Я уточню этот вопрос и чуть позже отпишу вам.",
    "Уточню детали и чуть позже напишу вам по этому вопросу.",
    "Я уточню информацию и немного позже дам вам ответ.",
    "Уточню этот момент и чуть позже вернусь к вам с ответом в чате.",
    "Я всё уточню и немного позже отпишу вам по этому вопросу.",
    "Уточню информацию по этому вопросу и чуть позже вам напишу.",
    "Я дополнительно уточню этот момент и чуть позже дам вам обратную связь.",
    "Уточню детали по этому вопросу и немного позже отпишу вам.",
    "Я уточню всё по этому вопросу и чуть позже вернусь к вам с ответом.",
)

_LEGACY_FALLBACK_PATTERNS = (
    r"уточню\s+у\s+коллег",
    r"вернусь\s+с\s+ответом",
    r"коллега\s+позвонит",
    r"передам\s+вопрос\s+коллег",
)

_CURRENT_FALLBACK_PATTERNS = tuple(
    re.escape(text.rstrip(".!?")) + r"[.!?]?"
    for text in UNKNOWN_KB_FALLBACK_VARIANTS
)

UNKNOWN_KB_FALLBACK_RE = re.compile(
    r"(?:"
    + "|".join(_LEGACY_FALLBACK_PATTERNS + _CURRENT_FALLBACK_PATTERNS)
    + r")",
    re.IGNORECASE,
)
LEGACY_KB_FALLBACK_RE = re.compile(
    r"(?:"
    + "|".join(_LEGACY_FALLBACK_PATTERNS)
    + r")",
    re.IGNORECASE,
)
APPROVED_UNKNOWN_KB_FALLBACK_RE = re.compile(
    r"(?:"
    + "|".join(_CURRENT_FALLBACK_PATTERNS)
    + r")",
    re.IGNORECASE,
)
PURE_APPROVED_UNKNOWN_KB_FALLBACK_RE = re.compile(
    r"^\s*(?:"
    + "|".join(_CURRENT_FALLBACK_PATTERNS)
    + r")\s*$",
    re.IGNORECASE,
)


def pick_unknown_kb_fallback() -> str:
    """Return one of the approved neutral fallback phrases."""
    return random.choice(UNKNOWN_KB_FALLBACK_VARIANTS)


def with_unknown_kb_fallback(prefix: Optional[str] = None) -> str:
    """Append a neutral fallback phrase after an optional factual prefix."""
    prefix_text = str(prefix or "").strip()
    fallback = pick_unknown_kb_fallback()
    if not prefix_text:
        return fallback
    if prefix_text[-1] not in ".!?":
        prefix_text += "."
    return f"{prefix_text} {fallback}"


def is_approved_unknown_kb_fallback(text: Optional[str]) -> bool:
    """Return True when text contains one of the approved neutral fallback variants."""
    return bool(APPROVED_UNKNOWN_KB_FALLBACK_RE.search(str(text or "")))


def is_pure_approved_unknown_kb_fallback(text: Optional[str]) -> bool:
    """Return True when text is exactly one approved neutral fallback variant."""
    return bool(PURE_APPROVED_UNKNOWN_KB_FALLBACK_RE.fullmatch(str(text or "").strip()))
