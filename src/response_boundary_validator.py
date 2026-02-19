"""
Response boundary validator (final guardrail before sending response).

Applies layered validation:
1. Detect violations
2. Optional single targeted retry (repair prompt)
3. Deterministic sanitization and fallback
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.feature_flags import flags
from src.logger import logger


@dataclass
class BoundaryValidationMetrics:
    total: int = 0
    violations_by_type: Dict[str, int] = field(default_factory=dict)
    retry_used: int = 0
    fallback_used: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "response_validation.total": self.total,
            "response_validation.violations_by_type": dict(self.violations_by_type),
            "response_validation.retry_used": self.retry_used,
            "response_validation.fallback_used": self.fallback_used,
        }


@dataclass
class BoundaryValidationResult:
    response: str
    violations: List[str] = field(default_factory=list)
    retry_used: bool = False
    fallback_used: bool = False
    validation_events: List[Dict[str, Any]] = field(default_factory=list)


class ResponseBoundaryValidator:
    """Universal post-validation guardrail for generated responses."""

    RUB_PATTERN = re.compile(r"(?iu)\bруб(?:\.|ля|лей|ль)?\b|₽")
    LEADING_ARTIFACT_PATTERN = re.compile(r"^\s*[\.\,\!\?]?\s*[—\-:]+\s*")
    DASH_AFTER_PUNCT_PATTERN = re.compile(r"([.!?])\s*[—\-]+\s*")
    MID_CONV_GREETING_PATTERN = re.compile(
        r'^(Здравствуйте|Добрый день|Добрый вечер|Доброе утро)[,!.]?\s*',
        re.IGNORECASE,
    )

    KNOWN_TYPO_FIXES = {
        "присылну": "пришлю",
    }

    KZ_PHONE_PATTERN = re.compile(r'(?:\+?[78])[\s\-\(]?\d{3}[\s\-\)]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}')
    IIN_PATTERN = re.compile(r'\b\d{12}\b')
    SEND_PROMISE_PATTERN = re.compile(
        r'(пришлю|отправлю|вышлю|скину).{0,40}(фото|видео|файл|документ|каталог)',
        re.IGNORECASE,
    )
    PAST_ACTION_PATTERN = re.compile(
        r'мы (уже |только что )?(отправили|выслали|прислали|связались|написали)',
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        self._metrics = BoundaryValidationMetrics()

    def reset_metrics(self) -> None:
        self._metrics = BoundaryValidationMetrics()

    def get_metrics(self) -> Dict[str, Any]:
        return self._metrics.to_dict()

    def validate_response(
        self,
        response: str,
        context: Optional[Dict[str, Any]] = None,
        llm: Any = None,
    ) -> BoundaryValidationResult:
        context = context or {}
        original = response or ""

        # Master switch.
        if not flags.is_enabled("response_boundary_validator"):
            return BoundaryValidationResult(response=original)

        initial_violations = self._detect_violations(original, context)
        if not initial_violations:
            return BoundaryValidationResult(response=original)

        self._metrics.total += 1
        self._increment_violations(initial_violations)
        events: List[Dict[str, Any]] = [
            {"stage": "detect", "violations": sorted(initial_violations)}
        ]

        # Hard hallucination violations → immediate deterministic fallback, no LLM retry.
        _HARD_HALLUCINATIONS = {"hallucinated_iin", "hallucinated_phone", "hallucinated_past_action"}
        if _HARD_HALLUCINATIONS & set(initial_violations):
            self._metrics.fallback_used += 1
            return BoundaryValidationResult(
                response=self._hallucination_fallback(),
                violations=sorted(initial_violations),
                retry_used=False,
                fallback_used=True,
                validation_events=events + [{"stage": "hallucination_fallback"}],
            )

        candidate = original
        retry_used = False

        # Single targeted retry.
        if (
            llm is not None
            and flags.is_enabled("response_boundary_retry")
        ):
            retry_used = True
            self._metrics.retry_used += 1
            repaired = self._retry_once(candidate, sorted(initial_violations), context, llm)
            if repaired:
                candidate = repaired
            events.append({"stage": "retry", "used": True})

        remaining = self._detect_violations(candidate, context)
        fallback_used = False

        if remaining:
            candidate = self._sanitize(candidate, context)
            remaining_after_sanitize = self._detect_violations(candidate, context)
            events.append(
                {
                    "stage": "sanitize",
                    "violations_before": sorted(remaining),
                    "violations_after": sorted(remaining_after_sanitize),
                }
            )
            if remaining_after_sanitize and flags.is_enabled("response_boundary_fallback"):
                candidate = self._deterministic_fallback(context)
                fallback_used = True
                self._metrics.fallback_used += 1
                events.append({"stage": "fallback", "used": True})

        logger.info(
            "Response boundary validation applied",
            violations=sorted(initial_violations),
            retry_used=retry_used,
            fallback_used=fallback_used,
        )
        logger.debug("Response boundary metrics", **self._metrics.to_dict())

        return BoundaryValidationResult(
            response=candidate,
            violations=sorted(initial_violations),
            retry_used=retry_used,
            fallback_used=fallback_used,
            validation_events=events,
        )

    def _detect_violations(self, response: str, context: Dict[str, Any]) -> List[str]:
        violations: List[str] = []

        if self._is_pricing_context(context) and self.RUB_PATTERN.search(response):
            violations.append("currency_locale")

        if ". —" in response or self.LEADING_ARTIFACT_PATTERN.match(response):
            violations.append("opening_punctuation")

        lower = response.lower()
        for typo in self.KNOWN_TYPO_FIXES:
            if typo in lower:
                violations.append("known_typos")
                break

        # IIN: 12-digit number not present in retrieved_facts
        if self.IIN_PATTERN.search(response):
            if not self.IIN_PATTERN.search(context.get("retrieved_facts", "")):
                violations.append("hallucinated_iin")

        # KZ/RU phone format not present in retrieved_facts
        if self.KZ_PHONE_PATTERN.search(response):
            if not self.KZ_PHONE_PATTERN.search(context.get("retrieved_facts", "")):
                violations.append("hallucinated_phone")

        # Promise to send a file/photo
        if self.SEND_PROMISE_PATTERN.search(response):
            violations.append("hallucinated_send_promise")

        # Fabricated past action
        if self.PAST_ACTION_PATTERN.search(response):
            violations.append("hallucinated_past_action")

        # Greeting opener is wrong in ANY non-greeting template (mid-conversation)
        _tmpl = context.get("selected_template", "")
        if "greeting" not in _tmpl and self.MID_CONV_GREETING_PATTERN.match(response):
            violations.append("mid_conversation_greeting")

        return violations

    def _sanitize(self, response: str, context: Dict[str, Any]) -> str:
        sanitized = response
        sanitized = self._sanitize_mid_conversation_greeting(sanitized, context)
        sanitized = self._sanitize_opening_punctuation(sanitized)
        sanitized = self._sanitize_known_typos(sanitized)
        sanitized = self._sanitize_send_promise(sanitized)
        if self._is_pricing_context(context):
            sanitized = self._sanitize_currency_locale(sanitized)
        return sanitized.strip()

    def _sanitize_currency_locale(self, response: str) -> str:
        response = response.replace("₽", "₸")
        return re.sub(self.RUB_PATTERN, "₸", response)

    def _sanitize_opening_punctuation(self, response: str) -> str:
        response = self.LEADING_ARTIFACT_PATTERN.sub("", response)
        response = self.DASH_AFTER_PUNCT_PATTERN.sub(r"\1 ", response)
        response = response.replace(". —", ". ")
        return re.sub(r"\s{2,}", " ", response).strip()

    def _sanitize_known_typos(self, response: str) -> str:
        fixed = response
        for typo, replacement in self.KNOWN_TYPO_FIXES.items():
            fixed = re.sub(rf"(?iu)\b{re.escape(typo)}\b", replacement, fixed)
        return fixed

    def _sanitize_send_promise(self, response: str) -> str:
        return self.SEND_PROMISE_PATTERN.sub(
            'Для фото и материалов — оставьте контакт, менеджер пришлёт вам всё.',
            response,
        )

    def _hallucination_fallback(self) -> str:
        return random.choice([
            "Уточню детали у коллег и вернусь с ответом.",
            "Этот момент уточню у специалиста — напишу вам.",
            "Передам вопрос команде и вернусь с точным ответом.",
        ])

    def _retry_once(
        self,
        response: str,
        violations: List[str],
        context: Dict[str, Any],
        llm: Any,
    ) -> Optional[str]:
        try:
            prompt = self._build_repair_prompt(response, violations, context)
            repaired = llm.generate(prompt)
            if not isinstance(repaired, str):
                return None
            return repaired.strip()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Response boundary retry failed", error=str(exc))
            return None

    def _sanitize_mid_conversation_greeting(self, response: str, context: Dict[str, Any]) -> str:
        if "greeting" in context.get("selected_template", ""):
            return response  # не трогаем начальное приветствие
        cleaned = self.MID_CONV_GREETING_PATTERN.sub("", response).strip()
        if len(cleaned) < 10:
            return response  # safety: не возвращать пустую/короткую строку
        if cleaned and cleaned[0].islower():
            cleaned = cleaned[0].upper() + cleaned[1:]
        return cleaned

    def _build_repair_prompt(
        self,
        response: str,
        violations: List[str],
        context: Dict[str, Any],
    ) -> str:
        rules = [
            "- Удали артефакты пунктуации вида '. —' и ведущие '-/—/:'.",
            "- Исправь опечатки.",
            "- Если ответ о цене, используй валюту ₸ и не используй руб/₽.",
        ]
        if "mid_conversation_greeting" in violations:
            rules.append(
                "- Убери приветствие в начале ответа ('Здравствуйте', 'Добрый день' и т.п.) "
                "— диалог уже начат, не здоровайся повторно."
            )
        return (
            "Переформулируй ответ, сохранив смысл.\n"
            "Исправь только проблемы качества границы ответа.\n"
            f"Нарушения: {', '.join(violations)}.\n"
            "Правила:\n"
            + "\n".join(rules) + "\n"
            + "Контекст:\n"
            f"intent={context.get('intent', '')}\n"
            f"action={context.get('action', '')}\n"
            f"selected_template={context.get('selected_template', '')}\n\n"
            "Исходный ответ:\n"
            f"{response}"
        )

    def _deterministic_fallback(self, context: Dict[str, Any]) -> str:
        if self._is_pricing_context(context):
            return "По стоимости сориентирую в ₸. Пришлю точный расчет под ваш кейс."
        return "Переформулирую коротко и по сути."

    def _is_pricing_context(self, context: Dict[str, Any]) -> bool:
        intent = str(context.get("intent", "")).lower()
        action = str(context.get("action", "")).lower()
        template = str(context.get("selected_template", "")).lower()
        retrieved_facts = str(context.get("retrieved_facts", "")).lower()

        pricing_signals = (
            "price" in intent
            or "pricing" in intent
            or "price" in action
            or "pricing" in action
            or "price" in template
            or "pricing" in template
            or "цен" in retrieved_facts
            or "тариф" in retrieved_facts
        )
        return pricing_signals

    def _increment_violations(self, violations: List[str]) -> None:
        for violation in violations:
            self._metrics.violations_by_type[violation] = (
                self._metrics.violations_by_type.get(violation, 0) + 1
            )


boundary_validator = ResponseBoundaryValidator()

