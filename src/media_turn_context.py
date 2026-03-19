"""Immutable media turn carrier and canonical media scrubber."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Mapping, Optional, Sequence

from src.immutable_types import FrozenDict


MEDIA_PROFILE_SAFE_FIELDS = {
    "contact_name",
    "company_name",
    "industry",
    "business_type",
    "city",
    "current_tools",
    "pain_point",
    "pain_category",
    "role",
}

_EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s\-()]{8,}\d)(?!\w)")
_IIN_RE = re.compile(r"\b\d{12}\b")
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b", re.IGNORECASE)
_IDENTIFIER_RE = re.compile(
    r"(?i)\b(?:"
    r"договор|контракт|сч[её]т|invoice|account|документ|паспорт|passport|iban|iin|инн"
    r")\s*(?:№|number|num|n|id|:|#)\s*[A-ZА-Я0-9][A-ZА-Я0-9/_-]{3,}\b"
)


@dataclass(frozen=True)
class MediaTurnContext:
    raw_user_text: str
    attachment_only: bool
    source_session_id: str
    source_user_id: str
    used_attachments: tuple[FrozenDict, ...] = ()
    skipped_attachments: tuple[FrozenDict, ...] = ()
    current_cards: tuple[FrozenDict, ...] = ()
    historical_candidates: tuple[FrozenDict, ...] = ()
    safe_extracted_data: FrozenDict = field(default_factory=lambda: FrozenDict({}))
    safe_media_facts: tuple[str, ...] = ()


def redact_media_text(text: Any) -> str:
    """Remove sensitive identifiers from media-derived text."""

    value = str(text or "").strip()
    if not value:
        return ""
    value = _EMAIL_RE.sub("[redacted]", value)
    value = _PHONE_RE.sub("[redacted]", value)
    value = _IIN_RE.sub("[redacted]", value)
    value = _IBAN_RE.sub("[redacted]", value)
    value = _IDENTIFIER_RE.sub("[redacted]", value)
    value = re.sub(r"\s{2,}", " ", value)
    return value.strip()


def scrub_media_fact_list(facts: Sequence[Any] | None, *, limit: int = 8) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in facts or ():
        value = redact_media_text(item)
        normalized = value.lower()
        if not value or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(value)
        if len(cleaned) >= limit:
            break
    return cleaned


def scrub_media_extracted_data(data: Mapping[str, Any] | None) -> dict[str, Any]:
    scrubbed: dict[str, Any] = {}
    for key, value in dict(data or {}).items():
        if key not in MEDIA_PROFILE_SAFE_FIELDS or value in (None, "", [], {}):
            continue
        if isinstance(value, str):
            value = redact_media_text(value)
            if not value:
                continue
        scrubbed[key] = value
    return scrubbed


def scrub_media_card_payload(card: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(card or {})
    if not payload:
        return {}

    return {
        "knowledge_id": str(payload.get("knowledge_id") or ""),
        "attachment_fingerprint": str(payload.get("attachment_fingerprint") or ""),
        "source_session_id": str(payload.get("source_session_id") or ""),
        "source_turn": int(payload.get("source_turn", 0) or 0),
        "file_name": str(payload.get("file_name") or ""),
        "media_kind": str(payload.get("media_kind") or ""),
        "source_user_text": str(payload.get("source_user_text") or "").strip(),
        "summary": redact_media_text(payload.get("summary")),
        "facts": scrub_media_fact_list(payload.get("facts", []) or [], limit=8),
        "extracted_data": scrub_media_extracted_data(payload.get("extracted_data", {}) or {}),
        "answer_context": redact_media_text(payload.get("answer_context")),
        "created_at": float(payload.get("created_at", 0.0) or 0.0),
        "updated_at": float(payload.get("updated_at", 0.0) or 0.0),
    }


def scrub_media_attachment_payload(attachment: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(attachment or {})
    if not payload:
        return {}

    scrubbed: dict[str, Any] = {}
    for key, value in payload.items():
        if value in (None, "", [], {}):
            continue
        if isinstance(value, str):
            scrubbed[key] = value.strip()
        else:
            scrubbed[key] = value
    return scrubbed


def freeze_media_value(value: Any) -> Any:
    if isinstance(value, FrozenDict):
        return value
    if isinstance(value, dict):
        return FrozenDict({key: freeze_media_value(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze_media_value(item) for item in value)
    return value


def freeze_media_turn_context(
    context: Optional[MediaTurnContext | Mapping[str, Any]],
) -> Optional[MediaTurnContext]:
    if context is None:
        return None

    if isinstance(context, MediaTurnContext):
        payload = context
    else:
        payload = MediaTurnContext(
            raw_user_text=str(context.get("raw_user_text") or ""),
            attachment_only=bool(context.get("attachment_only", False)),
            source_session_id=str(context.get("source_session_id") or ""),
            source_user_id=str(context.get("source_user_id") or ""),
            used_attachments=tuple(),
            skipped_attachments=tuple(),
            current_cards=tuple(),
            historical_candidates=tuple(),
            safe_extracted_data=FrozenDict({}),
            safe_media_facts=tuple(),
        )

    current_cards = [
        freeze_media_value(scrub_media_card_payload(card))
        for card in getattr(payload, "current_cards", ()) or ()
        if card
    ]
    historical_candidates = [
        freeze_media_value(scrub_media_card_payload(card))
        for card in getattr(payload, "historical_candidates", ()) or ()
        if card
    ]
    safe_extracted_data = freeze_media_value(
        scrub_media_extracted_data(getattr(payload, "safe_extracted_data", {}) or {})
    )
    safe_media_facts = tuple(
        scrub_media_fact_list(
            getattr(payload, "safe_media_facts", ()) or [
                fact
                for card in current_cards
                for fact in tuple(card.get("facts", ()) or ())
            ],
            limit=8,
        )
    )

    return MediaTurnContext(
        raw_user_text=str(getattr(payload, "raw_user_text", "") or ""),
        attachment_only=bool(getattr(payload, "attachment_only", False)),
        source_session_id=str(getattr(payload, "source_session_id", "") or ""),
        source_user_id=str(getattr(payload, "source_user_id", "") or ""),
        used_attachments=tuple(
            freeze_media_value(scrub_media_attachment_payload(item))
            for item in getattr(payload, "used_attachments", ()) or ()
            if item
        ),
        skipped_attachments=tuple(
            freeze_media_value(scrub_media_attachment_payload(item))
            for item in getattr(payload, "skipped_attachments", ()) or ()
            if item
        ),
        current_cards=tuple(current_cards),
        historical_candidates=tuple(historical_candidates),
        safe_extracted_data=safe_extracted_data,
        safe_media_facts=safe_media_facts,
    )
