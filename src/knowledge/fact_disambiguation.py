"""
Deterministic fact disambiguation for autonomous factual turns.

Goal:
- detect when retrieved facts contain conflicting entities with similar naming
  (e.g. tariff Pro vs kit Pro vs module Pro UKM),
- ask a narrow clarification question instead of risking a wrong factual answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from src.feature_flags import flags
from src.logger import logger
from src.settings import settings


_SECTION_RE = re.compile(
    r"^\[(?P<category>[^/\]]+)/(?P<topic>[^\]]+)\]\n(?P<body>.*?)(?=^\[[^/\]]+/[^\]]+\]\n|\Z)",
    re.MULTILINE | re.DOTALL,
)

_FAMILY_PATTERNS: Tuple[Tuple[str, re.Pattern], ...] = (
    ("mini", re.compile(r"\b(?:mini|мини)\b", re.IGNORECASE)),
    ("lite", re.compile(r"\b(?:lite|лайт)\b", re.IGNORECASE)),
    ("standard", re.compile(r"\b(?:standard|стандарт)\b", re.IGNORECASE)),
    ("pro", re.compile(r"\b(?:pro|про)\b", re.IGNORECASE)),
    ("business", re.compile(r"\bbusiness\b", re.IGNORECASE)),
    ("basic", re.compile(r"\bbasic\b", re.IGNORECASE)),
)

_FAMILY_ALIASES: Dict[str, str] = {
    "mini": "mini",
    "мини": "mini",
    "lite": "lite",
    "лайт": "lite",
    "standard": "standard",
    "стандарт": "standard",
    "pro": "pro",
    "про": "pro",
    "business": "business",
    "basic": "basic",
}
_FAMILY_CAPTURE = r"(?:mini|мини|lite|лайт|standard|стандарт|pro|про|business|basic)"
_INLINE_CANDIDATE_PATTERNS: Tuple[Tuple[str, re.Pattern], ...] = (
    (
        "tariff",
        re.compile(
            rf"(?:тариф|программн\w+\s+тариф)\s+(?P<family>{_FAMILY_CAPTURE})\b",
            re.IGNORECASE,
        ),
    ),
    (
        "kit",
        re.compile(
            rf"(?:комплект|кассовый\s+комплект)\s+(?P<family>{_FAMILY_CAPTURE})\b",
            re.IGNORECASE,
        ),
    ),
    (
        "module",
        re.compile(
            rf"(?:(?:wipon\s+)?(?P<family>{_FAMILY_CAPTURE})\s+(?:укм|модул\w*)|(?:модул\w*)\s+(?P<family_alt>{_FAMILY_CAPTURE}))",
            re.IGNORECASE,
        ),
    ),
)

_TYPE_PATTERNS: Tuple[Tuple[str, re.Pattern], ...] = (
    ("module", re.compile(r"(?:модул|укм|маркиров|акциз|алкогол)", re.IGNORECASE)),
    ("kit", re.compile(r"(?:комплект|оборудован|кассовый\s+комплект|моноблок|сканер|принтер)", re.IGNORECASE)),
    ("tariff", re.compile(r"(?:тариф|подписк|/\s*год|в\s+год|за\s+год|₸\s*/\s*год)", re.IGNORECASE)),
)

_MESSAGE_SPECIFIC_PATTERNS: Dict[str, re.Pattern] = {
    "tariff": re.compile(r"(?:\bтариф\b|программн\w+\s+тариф)", re.IGNORECASE),
    "kit": re.compile(r"(?:комплект|оборудован|моноблок|сканер|принтер|железо)", re.IGNORECASE),
    "module": re.compile(r"(?:модул|укм|маркиров|акциз|алкогол)", re.IGNORECASE),
}

# Implicit pricing signals: ценовой язык → tariff
_PRICING_SIGNAL_RE = re.compile(
    r"(?:цен[аы]|стоимост\w*|сколько\s+стоит|сколько\s+платить|оплат\w+"
    r"|подписк\w*|[вн]а?\s+год|за\s+год|₸\s*/\s*год|[вн]а?\s+месяц|за\s+месяц"
    r"|тариф\w*|лицензи\w*"
    r"|дешевл\w*|дорог\w*|бюджет\w*|рассрочк\w*)",
    re.IGNORECASE,
)

# Implicit equipment signals: оборудовательный язык → kit
# Намеренно исключены "купить"/"приобрести" — применимы и к тарифу, и к оборудованию.
_EQUIPMENT_SIGNAL_RE = re.compile(
    r"(?:оборудован\w*|моноблок\w*|сканер\w*|принтер\w*|устройств\w*"
    r"|железо|кассов\w+\s+аппарат|физическ\w*|железяк\w*)",
    re.IGNORECASE,
)

_CLARIFICATION_MARKER = "Ответьте номером 1-3 или напишите вариант словами."

# Russian preposition "про" (= "about") is indistinguishable from the product name
# "Про" by word-boundary rules alone.  When it appears before a NON-Pro product name
# (mini/lite/standard/basic/business) it is definitively a preposition and must NOT
# be counted as the Pro product family in step 3 of _detect_specific_type().
_PRO_PREPOSITION_RE = re.compile(
    r"\bпро\b(?=\s+(?:mini|мини|lite|лайт|standard|стандарт|basic|business)\b)",
    re.IGNORECASE,
)

# Regex to extract the family name from a clarification prompt.
_FAMILY_FROM_CLARIF_RE = re.compile(
    r"Уточните,\s*пожалуйста,\s*что\s+вы\s+имеете\s+в\s+виду\s+под\s+«([^»]+)»",
    re.IGNORECASE,
)
_NUMBERED_OPTION_RE = re.compile(r"(?m)^\s*([1-3])[\)\.\-]\s*(.+?)\s*$")


@dataclass
class FactSection:
    category: str
    topic: str
    body: str
    index: int


@dataclass
class FactCandidate:
    family: str
    entity_type: str
    display_name: str
    index: int


@dataclass
class FactDisambiguationDecision:
    should_disambiguate: bool = False
    clarification_text: str = ""
    options: List[str] = field(default_factory=list)
    reason_codes: List[str] = field(default_factory=list)
    family: str = ""


class FactDisambiguator:
    """Deterministic ambiguity detector for conflicting factual entities."""

    def __init__(self) -> None:
        self.strict_mode = bool(settings.get_nested("fact_disambiguation.strict_mode", True))
        self.max_options = int(settings.get_nested("fact_disambiguation.max_options", 3))
        self.max_context_sections = int(settings.get_nested("fact_disambiguation.max_context_sections", 5))
        self.max_clarification_repeats = int(
            settings.get_nested("fact_disambiguation.max_clarification_repeats", 2)
        )
        self.max_options = max(2, self.max_options)
        self.max_context_sections = max(1, self.max_context_sections)
        self.max_clarification_repeats = max(1, self.max_clarification_repeats)

    @staticmethod
    def is_enabled() -> bool:
        return bool(flags.is_enabled("response_fact_disambiguation"))

    def analyze(
        self,
        *,
        user_message: str,
        retrieved_facts: str,
        history: Optional[Sequence[Dict[str, str]]] = None,
    ) -> FactDisambiguationDecision:
        if not self.strict_mode:
            return FactDisambiguationDecision(reason_codes=["strict_mode_disabled"])

        message = str(user_message or "").strip()
        if not message:
            return FactDisambiguationDecision(reason_codes=["empty_user_message"])
        if not str(retrieved_facts or "").strip():
            return FactDisambiguationDecision(reason_codes=["empty_retrieved_facts"])

        if self._is_clarification_limit_reached(history or []):
            return FactDisambiguationDecision(reason_codes=["clarification_repeat_limit"])

        query_context = self._extract_query_context(str(retrieved_facts or ""))
        sections = self._parse_sections(query_context)[: self.max_context_sections]
        if not sections:
            return FactDisambiguationDecision(reason_codes=["no_query_sections"])

        candidates = self._extract_candidates(sections)
        if not candidates:
            return FactDisambiguationDecision(reason_codes=["no_canonical_candidates"])

        conflict_family, conflict_types = self._find_conflict_family(candidates)
        if not conflict_family:
            return FactDisambiguationDecision(reason_codes=["no_family_type_conflict"])

        specific_type = self._detect_specific_type(message)
        if specific_type and specific_type in conflict_types:
            return FactDisambiguationDecision(
                reason_codes=[f"message_specific_{specific_type}"],
                family=conflict_family,
            )

        # Fix 4: if this family was already clarified earlier in the conversation,
        # do not ask again — trust the earlier resolution.
        if conflict_family and self._is_family_already_clarified(history or [], conflict_family):
            return FactDisambiguationDecision(
                reason_codes=["family_already_clarified"],
                family=conflict_family,
            )

        options = self._build_options(candidates, conflict_family)
        if len(options) < 2:
            return FactDisambiguationDecision(reason_codes=["insufficient_options"], family=conflict_family)

        clarification = self._format_clarification(conflict_family, options)
        return FactDisambiguationDecision(
            should_disambiguate=True,
            clarification_text=clarification,
            options=options,
            family=conflict_family,
            reason_codes=[
                "family_type_conflict",
                f"family:{conflict_family}",
                f"types:{','.join(sorted(conflict_types))}",
            ],
        )

    @staticmethod
    def _extract_query_context(retrieved_facts: str) -> str:
        try:
            from src.knowledge.enhanced_retrieval import EnhancedRetrievalPipeline

            separator = EnhancedRetrievalPipeline.STATE_CONTEXT_SEPARATOR
        except Exception:
            separator = "\n=== КОНТЕКСТ ЭТАПА ===\n"
        return retrieved_facts.split(separator, 1)[0]

    def _parse_sections(self, text: str) -> List[FactSection]:
        sections: List[FactSection] = []
        for idx, match in enumerate(_SECTION_RE.finditer(text)):
            category = match.group("category").strip()
            topic = match.group("topic").strip()
            body = match.group("body").strip()
            sections.append(FactSection(category=category, topic=topic, body=body, index=idx))
        return sections

    def _extract_candidates(self, sections: Sequence[FactSection]) -> List[FactCandidate]:
        candidates: List[FactCandidate] = []
        seen: set = set()
        for section in sections:
            source_text = f"{section.topic}\n{section.body}"
            family = self._detect_family(source_text)
            entity_type = self._detect_entity_type(source_text)
            if not family or not entity_type:
                inline = self._extract_inline_candidates(text=source_text, index=section.index)
                for candidate in inline:
                    key = (candidate.family, candidate.entity_type, candidate.display_name)
                    if key in seen:
                        continue
                    seen.add(key)
                    candidates.append(candidate)
                continue

            display_name = self._build_display_name(
                family=family,
                entity_type=entity_type,
                text=source_text,
            )
            key = (family, entity_type, display_name)
            if key not in seen:
                seen.add(key)
                candidates.append(
                    FactCandidate(
                        family=family,
                        entity_type=entity_type,
                        display_name=display_name,
                        index=section.index,
                    )
                )

            inline = self._extract_inline_candidates(text=source_text, index=section.index)
            for candidate in inline:
                key = (candidate.family, candidate.entity_type, candidate.display_name)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(candidate)
        return candidates

    def _extract_inline_candidates(self, *, text: str, index: int) -> List[FactCandidate]:
        extracted: List[FactCandidate] = []
        for entity_type, pattern in _INLINE_CANDIDATE_PATTERNS:
            for match in pattern.finditer(text):
                raw_family = match.groupdict().get("family") or match.groupdict().get("family_alt")
                family = self._normalize_family(raw_family or "")
                if not family:
                    continue
                display_name = self._build_display_name(
                    family=family,
                    entity_type=entity_type,
                    text=match.group(0),
                )
                extracted.append(
                    FactCandidate(
                        family=family,
                        entity_type=entity_type,
                        display_name=display_name,
                        index=index,
                    )
                )
        return extracted

    @staticmethod
    def _normalize_family(raw_family: str) -> Optional[str]:
        token = str(raw_family or "").strip().lower()
        return _FAMILY_ALIASES.get(token)

    @staticmethod
    def _detect_family(text: str) -> Optional[str]:
        for family, pattern in _FAMILY_PATTERNS:
            if pattern.search(text):
                return family
        return None

    @staticmethod
    def _detect_entity_type(text: str) -> Optional[str]:
        for entity_type, pattern in _TYPE_PATTERNS:
            if pattern.search(text):
                return entity_type
        return None

    @staticmethod
    def _family_display(family: str) -> str:
        mapping = {
            "mini": "Mini",
            "lite": "Lite",
            "standard": "Standard",
            "pro": "Pro",
            "business": "Business",
            "basic": "Basic",
        }
        return mapping.get(family, family.title())

    def _build_display_name(self, *, family: str, entity_type: str, text: str) -> str:
        family_name = self._family_display(family)
        if entity_type == "tariff":
            return f"Тариф {family_name}"
        if entity_type == "kit":
            return f"Комплект {family_name}"
        if entity_type == "module":
            if re.search(r"\bукм\b", text, re.IGNORECASE):
                return f"Модуль {family_name} УКМ"
            return f"Модуль {family_name}"
        return f"{family_name} ({entity_type})"

    def _find_conflict_family(self, candidates: Sequence[FactCandidate]) -> Tuple[Optional[str], List[str]]:
        by_family: Dict[str, Dict[str, int]] = {}
        first_pos: Dict[str, int] = {}
        for candidate in candidates:
            by_family.setdefault(candidate.family, {})
            by_family[candidate.family][candidate.entity_type] = (
                by_family[candidate.family].get(candidate.entity_type, 0) + 1
            )
            first_pos[candidate.family] = min(first_pos.get(candidate.family, candidate.index), candidate.index)

        winner: Optional[str] = None
        winner_types: List[str] = []
        winner_score: Tuple[int, int, int] = (0, 0, 10_000)
        for family, type_counts in by_family.items():
            unique_types = [t for t in sorted(type_counts.keys())]
            if len(unique_types) < 2:
                continue
            score = (len(unique_types), sum(type_counts.values()), -first_pos.get(family, 10_000))
            if score > winner_score:
                winner = family
                winner_types = unique_types
                winner_score = score
        return winner, winner_types

    @staticmethod
    def _detect_specific_type(user_message: str) -> Optional[str]:
        # Step 1: explicit type words (highest priority)
        matched = [
            entity_type
            for entity_type, pattern in _MESSAGE_SPECIFIC_PATTERNS.items()
            if pattern.search(user_message)
        ]
        if len(matched) == 1:
            return matched[0]
        if len(matched) > 1:
            return None  # explicitly ambiguous — disambiguate

        # Step 2: implicit signals (pricing language → tariff; equipment language → kit)
        has_pricing = bool(_PRICING_SIGNAL_RE.search(user_message))
        has_equipment = bool(_EQUIPMENT_SIGNAL_RE.search(user_message))
        if has_pricing and not has_equipment:
            return "tariff"
        if has_equipment and not has_pricing:
            return "kit"

        # Step 3: 2+ product families mentioned → client is comparing tariffs
        # (nobody asks "Комплект Lite или Комплект Standard?" — only tariffs are compared)
        # Strip "про" when used as a preposition before a non-Pro product name
        # (e.g. "расскажите про Mini" → "про" = about, NOT the Pro product)
        msg_for_step3 = _PRO_PREPOSITION_RE.sub("", user_message)
        families_in_message = sum(
            1 for _fam, pat in _FAMILY_PATTERNS if pat.search(msg_for_step3)
        )
        if families_in_message >= 2:
            return "tariff"

        return None  # genuinely ambiguous — proceed to disambiguation

    def _build_options(self, candidates: Sequence[FactCandidate], family: str) -> List[str]:
        unique: List[str] = []
        seen: set = set()
        family_candidates = sorted(
            [candidate for candidate in candidates if candidate.family == family],
            key=lambda c: c.index,
        )
        for candidate in family_candidates:
            if candidate.display_name in seen:
                continue
            seen.add(candidate.display_name)
            unique.append(candidate.display_name)
            if len(unique) >= self.max_options:
                break
        return unique

    def _format_clarification(self, family: str, options: Sequence[str]) -> str:
        family_name = self._family_display(family)
        lines = [f"Уточните, пожалуйста, что вы имеете в виду под «{family_name}»:"]  # exact marker for parsing
        for idx, option in enumerate(options, start=1):
            lines.append(f"{idx}) {option}")
        lines.append(_CLARIFICATION_MARKER)
        return "\n".join(lines)

    def _is_clarification_limit_reached(self, history: Sequence[Dict[str, str]]) -> bool:
        if not history:
            return False
        count = 0
        for turn in reversed(list(history)):
            bot_text = str((turn or {}).get("bot", "") or "")
            if not bot_text.strip():
                break
            if _CLARIFICATION_MARKER in bot_text:
                count += 1
                if count >= self.max_clarification_repeats:
                    return True
                continue
            break
        return False

    def _is_family_already_clarified(
        self,
        history: Sequence[Dict[str, str]],
        conflict_family: str,
    ) -> bool:
        """True if this family was already clarified and the client gave a selection."""
        hist = list(history)
        for i, turn in enumerate(hist):
            bot_text = str((turn or {}).get("bot", "") or "")
            if _CLARIFICATION_MARKER not in bot_text:
                continue
            m = _FAMILY_FROM_CLARIF_RE.search(bot_text)
            if not m:
                continue
            clarified_display = m.group(1).strip().lower()
            # Normalise display name → internal family key
            found_family = next(
                (key for key, pat in _FAMILY_PATTERNS if pat.search(clarified_display)),
                None,
            )
            if found_family != conflict_family:
                continue
            # Check: the immediately following client turn looks like a selection
            if i + 1 >= len(hist):
                continue
            next_user = str((hist[i + 1] or {}).get("user", "") or "").strip()
            if not next_user:
                continue
            opts = [m2.group(2).strip() for m2 in _NUMBERED_OPTION_RE.finditer(bot_text)]
            is_numeric = bool(re.match(r"^\s*[1-3]\b", next_user))
            is_ordinal = bool(re.search(r"\b(?:перв|второ|треть)\w+\b", next_user, re.IGNORECASE))
            is_keyword = any(
                kw in next_user.lower()
                for kw in ("тариф", "комплект", "модул", "укм")
            )
            # Also check semantic match against the option texts
            is_option_text = any(
                opt.lower() in next_user.lower() or next_user.lower() in opt.lower()
                for opt in opts
            )
            if is_numeric or is_ordinal or is_keyword or is_option_text:
                return True
        return False


def detect_fact_disambiguation(
    *,
    user_message: str,
    retrieved_facts: str,
    history: Optional[Sequence[Dict[str, str]]] = None,
) -> FactDisambiguationDecision:
    """
    Safe wrapper around FactDisambiguator with fail-open behavior.
    """
    try:
        disambiguator = FactDisambiguator()
        if not disambiguator.is_enabled():
            return FactDisambiguationDecision(reason_codes=["feature_disabled"])
        return disambiguator.analyze(
            user_message=user_message,
            retrieved_facts=retrieved_facts,
            history=history,
        )
    except Exception as exc:  # pragma: no cover - defensive fail-open
        logger.warning("fact_disambiguation_failed_open", error=str(exc))
        return FactDisambiguationDecision(reason_codes=["detector_exception_fail_open"])
