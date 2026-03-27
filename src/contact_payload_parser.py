from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.conditions.state_machine.contact_validator import ContactValidator


EMAIL_PATTERN = re.compile(r"[\w\.-]+@[\w\.-]+\.\w{2,}", re.IGNORECASE)
IIN_WITH_MARKER_PATTERN = re.compile(r"(?:ИИН|ИНН)\s*:?\s*(\d{12})", re.IGNORECASE)
STANDALONE_IIN_PATTERN = re.compile(r"\b(\d{12})\b")
PHONE_PATTERNS = (
    re.compile(r"(?<!\d)\+7[\s\-\.]?\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{2}[\s\-\.]?\d{2}(?!\d)"),
    re.compile(r"(?<!\d)8[\s\-\.]?\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{2}[\s\-\.]?\d{2}(?!\d)"),
    re.compile(r"(?<!\d)7[\s\-\.]?\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{2}[\s\-\.]?\d{2}(?!\d)"),
    re.compile(r"(?<!\d)\d{3}[\s\-\.]\d{3}[\s\-\.]\d{2}[\s\-\.]\d{2}(?!\d)"),
    re.compile(r"(?<!\d)\d{10}(?!\d)"),
)
KASPI_MARKER_PATTERN = re.compile(r"(?:kaspi|каспи)", re.IGNORECASE)


@dataclass
class RawInlineContactPayload:
    phone_candidates: List[str] = field(default_factory=list)
    kaspi_phone_candidates: List[str] = field(default_factory=list)
    email_candidates: List[str] = field(default_factory=list)
    iin_candidates: List[str] = field(default_factory=list)


@dataclass
class InlineContactPayload:
    phone: Optional[str] = None
    kaspi_phone: Optional[str] = None
    email: Optional[str] = None
    iin: Optional[str] = None
    has_contact_payload: bool = False
    has_payment_payload: bool = False


def _dedupe_preserve_order(values: List[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def extract_inline_contact_spans(message: str) -> RawInlineContactPayload:
    text = str(message or "")
    raw = RawInlineContactPayload()

    raw.email_candidates = _dedupe_preserve_order([match.group(0) for match in EMAIL_PATTERN.finditer(text)])

    marked_iins = [match.group(1) for match in IIN_WITH_MARKER_PATTERN.finditer(text)]
    standalone_iins = [match.group(1) for match in STANDALONE_IIN_PATTERN.finditer(text)]
    raw.iin_candidates = _dedupe_preserve_order(marked_iins + standalone_iins)

    phone_candidates: List[str] = []
    for pattern in PHONE_PATTERNS:
        phone_candidates.extend(match.group(0) for match in pattern.finditer(text))
    raw.phone_candidates = _dedupe_preserve_order(phone_candidates)

    kaspi_candidates: List[str] = []
    for marker in KASPI_MARKER_PATTERN.finditer(text):
        window = text[marker.end(): marker.end() + 40]
        for pattern in PHONE_PATTERNS:
            match = pattern.search(window)
            if match:
                kaspi_candidates.append(match.group(0))
                break
    raw.kaspi_phone_candidates = _dedupe_preserve_order(kaspi_candidates)
    return raw


def normalize_inline_contact_payload(
    raw: RawInlineContactPayload,
    validator: Optional["ContactValidator"] = None,
) -> InlineContactPayload:
    if validator is None:
        from src.conditions.state_machine.contact_validator import ContactValidator

        validator = ContactValidator()
    payload = InlineContactPayload()

    for candidate in raw.email_candidates:
        email = validator.validate_email(candidate)
        if email.is_valid:
            payload.email = email.normalized_value
            break

    for candidate in raw.phone_candidates:
        phone = validator.validate_phone(candidate)
        if phone.is_valid:
            payload.phone = phone.normalized_value
            break

    for candidate in raw.kaspi_phone_candidates:
        phone = validator.validate_phone(candidate)
        if phone.is_valid:
            payload.kaspi_phone = phone.normalized_value
            if not payload.phone:
                payload.phone = phone.normalized_value
            break

    if raw.iin_candidates:
        payload.iin = raw.iin_candidates[0]

    payload.has_contact_payload = bool(payload.phone or payload.kaspi_phone or payload.email)
    payload.has_payment_payload = bool(payload.iin and (payload.phone or payload.kaspi_phone))
    return payload


def parse_inline_contact_payload(
    message: str,
    validator: Optional["ContactValidator"] = None,
) -> InlineContactPayload:
    return normalize_inline_contact_payload(
        extract_inline_contact_spans(message),
        validator=validator,
    )
