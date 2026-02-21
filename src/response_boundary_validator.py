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
    SEND_CAPABILITY_PATTERN = re.compile(
        r'(?:я\s+)?(?:могу|можем|сможем).{0,25}(?:отправить|выслать|прислать|скинуть)'
        r'.{0,40}(?:фото|видео|файл|документ|скриншот|каталог)',
        re.IGNORECASE,
    )
    PAST_ACTION_PATTERN = re.compile(
        r'мы (уже |только что )?(отправили|выслали|прислали|связались|написали|подготовили|оформили)',
        re.IGNORECASE,
    )
    PAST_SETUP_PATTERN = re.compile(
        r'(?:уже\s+)?(?:всё\s+)?(?:подключ(?:ил(?:и)?|ен[аоы]?|ено)|'
        r'настро(?:ил(?:и)?|ен[аоы]?|ено)|'
        r'активир(?:овал(?:и)?|ован[аоы]?|овано)|'
        r'готов[аоы]?\s+к\s+работе)',
        re.IGNORECASE,
    )
    INVOICE_WITHOUT_IIN_PATTERN = re.compile(
        r'(?:сч[её]т|договор).{0,40}без\s+иин',
        re.IGNORECASE,
    )
    INVOICE_PROMISE_PATTERN = re.compile(
        r'(?:выстав(?:им|лю|ить)|оформ(?:им|лю|ить)|подготов(?:им|лю|ить)).{0,24}(?:сч[её]т|договор)',
        re.IGNORECASE,
    )
    DEMO_WITHOUT_CONTACT_PATTERN = re.compile(
        r'(?:отправ(?:им|лю|ить)|покаж(?:ем|у|у?ть)|организуем|провед(?:ем|у|у?ть)).{0,40}'
        r'(?:демо|презентац).{0,24}без\s+контакт',
        re.IGNORECASE,
    )
    # Bot giving client's own phone back as "manager's contact" — always wrong
    MANAGER_CONTACT_GIVEOUT_PATTERN = re.compile(
        r'(?:контакт|телефон|номер)\s+менеджера\s*:\s*[+\d]',
        re.IGNORECASE,
    )
    # Bot fabricating a named client/company testimonial ("наш клиент из «X»", "компания «X»")
    FAKE_CLIENT_NAME_PATTERN = re.compile(
        r'(?:'
        r'(?:наш(?:его|их)?\s+)?клиент(?:ов|а)?\s+(?:из\s+)?(?:\w+\s+){0,3}[«"\']\w'
        r'|'
        r'компани[яи]\s+[«"\'][^«"\']{2,}'
        r'|'
        r'(?:сеть\s+магазин\w*|предприятие)\s+[«"\'][^«"\']{2,}'
        r')',
        re.IGNORECASE,
    )
    QUANT_CLAIM_PATTERN = re.compile(
        r'(?iu)\b(\d{1,3}(?:[.,]\d+)?)\s*(%|процент(?:а|ов)?|раз(?:а)?|'
        r'минут(?:ы)?|час(?:а|ов)?|дн(?:я|ей)?|недел(?:и|ь)|месяц(?:а|ев)?)\b'
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
        _HARD_HALLUCINATIONS = {"hallucinated_iin", "hallucinated_phone", "hallucinated_past_action", "hallucinated_manager_contact", "hallucinated_client_name"}
        if _HARD_HALLUCINATIONS & set(initial_violations):
            self._metrics.fallback_used += 1
            _ctx_with_violations = {**context, "violations": sorted(initial_violations)}
            return BoundaryValidationResult(
                response=self._hallucination_fallback(_ctx_with_violations),
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

        # IIN: 12-digit number not grounded in retrieved_facts/user_message/collected_data
        for m in self.IIN_PATTERN.finditer(response):
            if not self._is_number_grounded(m.group(0), context):
                violations.append("hallucinated_iin")
                break

        # Phone: not grounded in retrieved_facts/user_message/collected_data
        for m in self.KZ_PHONE_PATTERN.finditer(response):
            if not self._is_number_grounded(m.group(0), context):
                violations.append("hallucinated_phone")
                break

        # Promise to send a file/photo
        if self.SEND_PROMISE_PATTERN.search(response) or self.SEND_CAPABILITY_PATTERN.search(response):
            violations.append("hallucinated_send_promise")

        # Fabricated past action
        if self.PAST_ACTION_PATTERN.search(response) or self.PAST_SETUP_PATTERN.search(response):
            violations.append("hallucinated_past_action")

        collected = context.get("collected_data", {})
        if not isinstance(collected, dict):
            collected = {}

        # Business-constraint violation: invoice/contract without IIN
        if self.INVOICE_WITHOUT_IIN_PATTERN.search(response):
            violations.append("invoice_without_iin")
        elif self.INVOICE_PROMISE_PATTERN.search(response) and not collected.get("iin"):
            violations.append("invoice_without_iin")

        # Promise to run/send demo while explicitly having no contact data.
        if (
            self.DEMO_WITHOUT_CONTACT_PATTERN.search(response)
            and not (collected.get("contact_info") or collected.get("kaspi_phone"))
        ):
            violations.append("demo_without_contact")

        # Bot presenting client's own phone as "manager's contact" number
        if self.MANAGER_CONTACT_GIVEOUT_PATTERN.search(response):
            violations.append("hallucinated_manager_contact")

        # Bot fabricating named client testimonial not grounded in retrieved_facts
        if self.FAKE_CLIENT_NAME_PATTERN.search(response):
            retrieved = str(context.get("retrieved_facts", ""))
            # Only flag if the pattern fires but the full phrase isn't in retrieved_facts
            m = self.FAKE_CLIENT_NAME_PATTERN.search(response)
            if m and m.group(0)[:20] not in retrieved:
                violations.append("hallucinated_client_name")

        # Greeting opener is wrong in ANY non-greeting template (mid-conversation)
        _tmpl = context.get("selected_template", "")
        if "greeting" not in _tmpl and self.MID_CONV_GREETING_PATTERN.match(response):
            violations.append("mid_conversation_greeting")

        # Ungrounded short numeric claims (e.g., "в 3 раза", "70%", "15 минут")
        if self._has_ungrounded_quant_claim(response, context):
            violations.append("ungrounded_quant_claim")

        return violations

    @staticmethod
    def _normalize_digits(value: str) -> str:
        return re.sub(r"\D", "", str(value or ""))

    @staticmethod
    def _iter_scalar_values(value: Any) -> List[str]:
        out: List[str] = []
        if value is None:
            return out
        if isinstance(value, dict):
            for v in value.values():
                out.extend(ResponseBoundaryValidator._iter_scalar_values(v))
            return out
        if isinstance(value, (list, tuple, set)):
            for v in value:
                out.extend(ResponseBoundaryValidator._iter_scalar_values(v))
            return out
        out.append(str(value))
        return out

    def _extract_grounded_numbers(self, context: Dict[str, Any]) -> List[str]:
        grounded_sources: List[str] = []
        grounded_sources.extend(self._iter_scalar_values(context.get("retrieved_facts", "")))
        grounded_sources.extend(self._iter_scalar_values(context.get("user_message", "")))
        grounded_sources.extend(self._iter_scalar_values(context.get("collected_data", {})))

        grounded_numbers: List[str] = []
        pattern = re.compile(r"(?:\+?[78][\d\s\-\(\)]{9,})|\b\d{10,12}\b")
        for text in grounded_sources:
            for m in pattern.finditer(text):
                normalized = self._normalize_digits(m.group(0))
                if len(normalized) >= 10:
                    grounded_numbers.append(normalized)
        return grounded_numbers

    def _is_number_grounded(self, raw_number: str, context: Dict[str, Any]) -> bool:
        candidate = self._normalize_digits(raw_number)
        if len(candidate) < 10:
            return True
        grounded_numbers = self._extract_grounded_numbers(context)
        for known in grounded_numbers:
            if candidate == known:
                return True
            # Allow formatting/country-code differences by last 10 digits for phones
            if len(candidate) >= 10 and len(known) >= 10 and candidate[-10:] == known[-10:]:
                return True
        return False

    def _has_ungrounded_quant_claim(self, response: str, context: Dict[str, Any]) -> bool:
        """
        Detect short numeric KPI/time claims that are absent from grounding context.
        """
        text = str(response or "")
        if not text:
            return False

        grounding_blob = " ".join(
            self._iter_scalar_values(context.get("retrieved_facts", ""))
            + self._iter_scalar_values(context.get("user_message", ""))
        )
        if not grounding_blob:
            grounding_blob = ""

        for match in self.QUANT_CLAIM_PATTERN.finditer(text):
            raw_num = match.group(1).replace(",", ".")
            # Ignore explicit 1x style that can be conversationally benign.
            try:
                value = float(raw_num)
            except ValueError:
                continue
            if value <= 1.0:
                continue
            # Claim considered grounded only if exact number+unit appears in facts/user message.
            if match.group(0).lower() not in grounding_blob.lower():
                return True
        return False

    def _sanitize(self, response: str, context: Dict[str, Any]) -> str:
        sanitized = response
        sanitized = self._sanitize_mid_conversation_greeting(sanitized, context)
        sanitized = self._sanitize_opening_punctuation(sanitized)
        sanitized = self._sanitize_known_typos(sanitized)
        sanitized = self._sanitize_send_promise(sanitized)
        sanitized = self._sanitize_invoice_without_iin(sanitized)
        sanitized = self._sanitize_demo_without_contact(sanitized)
        sanitized = self._sanitize_ungrounded_quant_claim(sanitized)
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
        safe_send = 'Для фото и материалов — оставьте контакт, менеджер пришлёт вам всё.'
        safe_setup = 'Подключение выполняет менеджер после согласования деталей.'
        if (
            self.SEND_PROMISE_PATTERN.search(response)
            or self.SEND_CAPABILITY_PATTERN.search(response)
            or self.PAST_SETUP_PATTERN.search(response)
        ):
            return (
                "В чате я не отправляю файлы и не подтверждаю подключение. "
                "Могу передать запрос менеджеру — оставьте контакт."
            )
        sanitized = self.SEND_PROMISE_PATTERN.sub(safe_send, response)
        sanitized = self.SEND_CAPABILITY_PATTERN.sub(safe_send, sanitized)
        sanitized = self.PAST_SETUP_PATTERN.sub(safe_setup, sanitized)
        return sanitized

    def _sanitize_invoice_without_iin(self, response: str) -> str:
        if self.INVOICE_WITHOUT_IIN_PATTERN.search(response) or self.INVOICE_PROMISE_PATTERN.search(response):
            return (
                "Для выставления счёта нужен ИИН и номер телефона Kaspi. "
                "Если сейчас неудобно, можем вернуться к оформлению позже."
            )
        return response

    def _sanitize_demo_without_contact(self, response: str) -> str:
        if self.DEMO_WITHOUT_CONTACT_PATTERN.search(response):
            return (
                "Для демо нужен контакт, чтобы менеджер согласовал удобное время. "
                "Если контакт пока не готовы дать, могу кратко ответить на вопросы здесь."
            )
        return response

    def _sanitize_ungrounded_quant_claim(self, response: str) -> str:
        if self.QUANT_CLAIM_PATTERN.search(response):
            return (
                "Опишу без неподтверждённых цифр: Wipon помогает упростить учёт и снизить ручную нагрузку. "
                "Точные метрики и сроки уточним по вашему кейсу."
            )
        return response

    def _hallucination_fallback(self, context: Optional[Dict[str, Any]] = None) -> str:
        ctx = context or {}
        intent = str(ctx.get("intent", "")).lower()
        state = str(ctx.get("state", "")).lower()
        if intent == "contact_provided" and state == "payment_ready":
            return (
                "Данные получены — ИИН и телефон Kaspi зафиксированы. "
                "Менеджер свяжется с вами для подтверждения оплаты."
            )
        if intent in {"contact_provided", "callback_request", "demo_request"}:
            return (
                "Контакт получил. Следующий шаг — менеджер свяжется с вами "
                "и согласует удобное время."
            )
        # Payment/closing context: ask for missing data without hallucinating it
        if intent == "payment_confirmation" or state == "autonomous_closing":
            return (
                "Для оплаты через Kaspi нужны ваш ИИН и номер Kaspi. "
                "Пожалуйста, укажите их — и мы сразу оформим подписку."
            )
        # Discovery/early stage: neutral helpful response
        if state in {"autonomous_discovery", "greeting"} or intent in {"situation_provided", "greeting"}:
            return "Расскажите подробнее о вашем бизнесе — это поможет мне предложить оптимальное решение."
        violations = ctx.get("violations", [])
        if "hallucinated_client_name" in violations:
            return (
                "Наши клиенты отмечают стабильную работу системы — в том числе в условиях плохого "
                "интернета и большой нагрузки. Хотите убедиться сами — предлагаем демо-доступ?"
            )
        if self._is_pricing_context(ctx):
            return "По стоимости сориентирую в ₸. Подготовлю точный расчет под ваш кейс."
        return "Переформулирую коротко и по сути."

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
        if "ungrounded_quant_claim" in violations:
            rules.append(
                "- Удали неподтверждённые цифры и метрики (проценты, 'в N раз', минуты/часы/дни), "
                "если их нет в фактах контекста."
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
        intent = str(context.get("intent", "")).lower()
        if intent == "request_brevity":
            return (
                "Коротко: внутренние настройки не раскрываю. "
                "Могу ответить по продукту, цене и внедрению."
            )
        if intent in {"contact_provided", "callback_request", "demo_request"}:
            return (
                "Контакт получил. Следующий шаг — менеджер свяжется с вами "
                "и согласует удобное время."
            )
        if self._is_pricing_context(context):
            return "По стоимости сориентирую в ₸. Пришлю точный расчет под ваш кейс."
        return "Коротко по делу: помогу выбрать следующий шаг под ваш кейс."

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
