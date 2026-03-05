"""
Same-model factual verifier for autonomous responses.

Runs an isolated verification pass against retrieved KB facts using the same LLM
via structured output. If the candidate response is not grounded, it rewrites
the answer to a DB-grounded variant without handoff/fallback phrases.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import re
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field

from src.feature_flags import flags
from src.logger import logger
from src.settings import settings


class ClaimCheck(BaseModel):
    claim: str = Field(default="", max_length=300)
    supported: bool = False
    evidence_quote: str = Field(default="", max_length=240)


class VerifierOutput(BaseModel):
    verdict: Literal["pass", "fail"]   # required — ensures Ollama generates an object
    checks: List[ClaimCheck] = Field(default_factory=list)
    rewritten_response: str = Field(default="", max_length=1500)
    confidence: float = Field(default=0.0, ge=0.0)


@dataclass
class VerificationResult:
    final_response: str
    changed: bool
    verifier_used: bool
    verifier_verdict: str
    reason_codes: List[str] = field(default_factory=list)
    fallback_required: bool = False


class FactualVerifier:
    """Isolated factual verification pass over a generated response."""

    _HIGH_RISK_RESPONSE_RE = re.compile(
        r"(?:₸|тенге|тг|\b\d[\d\s]{2,}\b|стоим|цена|тариф|в\s+месяц|в\s+год)",
        re.IGNORECASE,
    )
    _FORBIDDEN_FALLBACK_RE = re.compile(
        r"(?:уточню\s+у\s+коллег|вернусь\s+с\s+ответом|коллега\s+позвонит|передам\s+вопрос\s+коллег)",
        re.IGNORECASE,
    )
    _TERM_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9-]{3,}")
    _QUERY_CONTEXT_SEPARATOR_RE = re.compile(r"\n===\s*КОНТЕКСТ\s+ЭТАПА\s*===\n", re.IGNORECASE)
    _EMPTY_CONTEXT_RE = re.compile(r"^\(\s*response[_\s]context\s+empty\s*\)$", re.IGNORECASE)
    _SECTION_HEADER_RE = re.compile(r"^\[[^]\n]+/[^]\n]+\]$")
    _STRUCTURAL_LINE_RE = re.compile(
        r"^(?:параметры|основная\s+функция|получатель\s+данных|дополнительно)\s*:?$",
        re.IGNORECASE,
    )
    _ABSTRACT_SENTENCE_RE = re.compile(
        r"(?:\bобзор\b|\bсценарий\b|\bвозможност\w*\b|\bпреимуществ\w*\b|"
        r"\bфункци\w*\b|\bпредложени\w*\b|\bпакет\w*\b|\bрешени\w*\b)",
        re.IGNORECASE,
    )
    _CITY_RE = re.compile(
        r"\b(?:алматы|астан\w*|шымкент|актау|караганд\w*|павлодар|актобе|костанай|атырау)\b",
        re.IGNORECASE,
    )
    _QUERY_STOP_WORDS = frozenset({
        "это", "как", "что", "где", "когда", "какие", "какой", "какая", "какое",
        "мне", "нас", "вам", "тут", "там", "или", "если", "для", "про", "под",
        "при", "все", "всё", "есть", "можно", "надо", "нужно", "сколько",
        "стоит", "стоимость", "цена", "расскажите", "подскажите", "хочу",
        "узнать", "понять", "интересует",
    })

    def __init__(self, llm: Any) -> None:
        self.llm = llm
        self.enabled = bool(settings.get_nested("factual_verifier.enabled", True))
        self.scope = str(settings.get_nested("factual_verifier.scope", "factual_only") or "factual_only")
        self.max_facts_chars = int(settings.get_nested("factual_verifier.max_facts_chars", 7000))
        self.temperature = float(settings.get_nested("factual_verifier.temperature", 0.1))
        self.max_claims = int(settings.get_nested("factual_verifier.max_claims", 6))
        self.rewrite_on_fail = bool(settings.get_nested("factual_verifier.rewrite_on_fail", True))
        # Backward-compatible setting parse. Verifier no longer emits handoff fallbacks.
        self.fallback_on_failed_rewrite = bool(
            settings.get_nested("factual_verifier.fallback_on_failed_rewrite", False)
        )

    def is_enabled(self) -> bool:
        return self.enabled and flags.is_enabled("response_factual_verifier")

    def verify_and_rewrite(
        self,
        *,
        user_message: str,
        candidate_response: str,
        retrieved_facts: str,
        intent: str,
        state: str,
        dialog_history: Optional[List[dict]] = None,
    ) -> VerificationResult:
        original = str(candidate_response or "").strip()
        facts_text = str(retrieved_facts or "").strip()
        if not original:
            return VerificationResult(
                final_response=original,
                changed=False,
                verifier_used=False,
                verifier_verdict="not_run",
                reason_codes=["empty_response"],
            )
        if not self.is_enabled():
            return VerificationResult(
                final_response=original,
                changed=False,
                verifier_used=False,
                verifier_verdict="not_run",
                reason_codes=["disabled"],
            )
        if not facts_text:
            return VerificationResult(
                final_response=original,
                changed=False,
                verifier_used=False,
                verifier_verdict="not_run",
                reason_codes=["empty_facts"],
            )
        if not hasattr(self.llm, "generate_structured"):
            return VerificationResult(
                final_response=original,
                changed=False,
                verifier_used=False,
                verifier_verdict="not_run",
                reason_codes=["structured_unavailable"],
            )

        facts_text = facts_text[: self.max_facts_chars]
        first = self._verify_once(
            user_message=user_message,
            candidate_response=original,
            retrieved_facts=facts_text,
            intent=intent,
            state=state,
            allow_rewrite=self.rewrite_on_fail,
            dialog_history=dialog_history,
        )
        if first is None:
            reason_codes: List[str] = ["llm_error"]
            llm_rewrite = self._attempt_llm_kb_rewrite_with_verify(
                user_message=user_message,
                retrieved_facts=facts_text,
                intent=intent,
                state=state,
                dialog_history=dialog_history,
            )
            if llm_rewrite is not None:
                rewritten_text, rewrite_reason = llm_rewrite
                reason_codes.append(rewrite_reason)
                return VerificationResult(
                    final_response=rewritten_text,
                    changed=(rewritten_text != original),
                    verifier_used=True,
                    verifier_verdict="pass",
                    reason_codes=reason_codes,
                )
            reason_codes.append("safe_minimal_fallback")
            return VerificationResult(
                final_response=self._build_safe_minimal_response(user_message=user_message),
                changed=True,
                verifier_used=True,
                verifier_verdict="error",
                reason_codes=reason_codes,
            )

        if first.verdict == "pass":
            cleaned = self._ensure_no_forbidden_fallback(
                original,
                user_message=user_message,
                retrieved_facts=facts_text,
            )
            return VerificationResult(
                final_response=cleaned,
                changed=(cleaned != original),
                verifier_used=True,
                verifier_verdict="pass",
                reason_codes=["pass_sanitized" if cleaned != original else "pass"],
            )

        reason_codes: List[str] = ["initial_fail"]
        unsupported = sum(1 for chk in first.checks if not chk.supported)
        if unsupported:
            reason_codes.append(f"unsupported_claims:{unsupported}")

        rewritten = str(first.rewritten_response or "").strip()
        if self.rewrite_on_fail and rewritten:
            second = self._verify_once(
                user_message=user_message,
                candidate_response=rewritten,
                retrieved_facts=facts_text,
                intent=intent,
                state=state,
                allow_rewrite=False,
                dialog_history=dialog_history,
            )
            if second is not None and second.verdict == "pass":
                cleaned_rewrite = self._ensure_no_forbidden_fallback(
                    rewritten,
                    user_message=user_message,
                    retrieved_facts=facts_text,
                )
                reason_codes.append("rewrite_pass")
                return VerificationResult(
                    final_response=cleaned_rewrite,
                    changed=(cleaned_rewrite != original),
                    verifier_used=True,
                    verifier_verdict="pass",
                    reason_codes=reason_codes,
                )
            reason_codes.append("rewrite_failed")
        elif self.rewrite_on_fail:
            reason_codes.append("rewrite_empty")

        # Fallback policy: fail verdict must never ship unchecked rewrite.
        # Try a dedicated LLM-only KB rewrite + verify pass before safe minimal fallback.
        llm_rewrite = self._attempt_llm_kb_rewrite_with_verify(
            user_message=user_message,
            retrieved_facts=facts_text,
            intent=intent,
            state=state,
            dialog_history=dialog_history,
        )
        if llm_rewrite is not None:
            rewritten_text, rewrite_reason = llm_rewrite
            reason_codes.append(rewrite_reason)
            return VerificationResult(
                final_response=rewritten_text,
                changed=(rewritten_text != original),
                verifier_used=True,
                verifier_verdict="pass",
                reason_codes=reason_codes,
                fallback_required=False,
            )

        safe_minimal = self._build_safe_minimal_response(user_message=user_message)
        reason_codes.append("safe_minimal_fallback")
        return VerificationResult(
            final_response=safe_minimal,
            changed=(safe_minimal != original),
            verifier_used=True,
            verifier_verdict="fail",
            reason_codes=reason_codes,
            fallback_required=False,
        )

    def _verify_once(
        self,
        *,
        user_message: str,
        candidate_response: str,
        retrieved_facts: str,
        intent: str,
        state: str,
        allow_rewrite: bool,
        dialog_history: Optional[List[dict]] = None,
    ) -> Optional[VerifierOutput]:
        mode = "rewrite" if allow_rewrite else "verify_only"
        prompt = self._build_prompt(
            user_message=user_message,
            candidate_response=candidate_response,
            retrieved_facts=retrieved_facts,
            intent=intent,
            state=state,
            mode=mode,
            dialog_history=dialog_history,
        )
        try:
            result = self.llm.generate_structured(
                prompt=prompt,
                schema=VerifierOutput,
                allow_fallback=False,
                purpose="factual_verifier",
                temperature=self.temperature,
                num_predict=800,
            )
            if isinstance(result, VerifierOutput):
                return result
            return None
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Factual verifier structured call failed", error=str(exc))
            return None

    def verify_only(
        self,
        *,
        user_message: str,
        candidate_response: str,
        retrieved_facts: str,
        intent: str,
        state: str,
        dialog_history: Optional[List[dict]] = None,
    ) -> Optional[VerifierOutput]:
        """Run a strict verify-only pass (no rewrite) for an already-mutated response."""
        response = str(candidate_response or "").strip()
        facts_text = str(retrieved_facts or "").strip()
        if not response or not facts_text:
            return None
        if not self.is_enabled():
            return None
        if not hasattr(self.llm, "generate_structured"):
            return None
        facts_text = facts_text[: self.max_facts_chars]
        result = self._verify_once(
            user_message=user_message,
            candidate_response=response,
            retrieved_facts=facts_text,
            intent=intent,
            state=state,
            allow_rewrite=False,
            dialog_history=dialog_history,
        )
        return result

    def _build_prompt(
        self,
        *,
        user_message: str,
        candidate_response: str,
        retrieved_facts: str,
        intent: str,
        state: str,
        mode: str,
        dialog_history: Optional[List[dict]] = None,
    ) -> str:
        rewrite_policy = (
            "Если verdict=fail, перепиши ответ строго по фактам из KB. "
            "Если по части запроса в KB нет данных, убери неподтвержденные части "
            "и оставь только подтвержденные факты. Фразы про коллег и перезвон недопустимы."
            if mode == "rewrite"
            else "НЕ переписывай ответ: поле rewritten_response оставь пустым."
        )
        completeness_policy = (
            "КРИТЕРИЙ ПОЛНОТЫ: если клиент явно просит полный перечень/все варианты/полное сравнение, "
            "verdict=pass только когда ответ покрывает все релевантные пункты из KB_CONTEXT "
            "или явно честно ограничивает охват (например: «в KB есть только ...»).\n"
        )

        history_block = ""
        if dialog_history:
            lines = []
            for entry in dialog_history[-4:]:
                user_txt = str(entry.get("user", "") or "").strip()
                bot_txt = str(entry.get("bot", "") or "").strip()
                if not user_txt and not bot_txt:
                    continue
                block = ""
                if user_txt:
                    block += f"Клиент: {user_txt[:200]}\n"
                if bot_txt:
                    block += f"Бот: {bot_txt[:200]}\n"
                if block:
                    lines.append(block.strip())
            if lines:
                history_block = "ИСТОРИЯ (последние ходы):\n" + "\n".join(lines) + "\n\n"

        return (
            "Ты factual-verifier для ответа менеджера.\n"
            "Проверь ТОЛЬКО соответствие ответа фактам из KB_CONTEXT.\n"
            "Нельзя использовать внешние знания.\n"
            "Правила проверки утверждений:\n"
            "  supported=true: прямое подтверждение в KB, парафраз KB, логический вывод из KB без добавления новых чисел.\n"
            "  supported=false: утверждение явно противоречит KB ИЛИ добавляет конкретные цифры/названия/даты которых нет в KB.\n"
            "КРИТЕРИЙ РЕЛЕВАНТНОСТИ: verdict=fail, если ответ уходит от вопроса клиента или подменяет тему.\n"
            "  НЕ ПРОВЕРЯТЬ: разговорные конструкции, оценки, переходы, риторические фразы\n"
            "  (например: «отлично подойдёт», «хороший выбор», «давайте разберёмся», «для вашего формата»).\n"
            "  Это не фактические утверждения — игнорировать при проверке claims.\n"
            f"{completeness_policy}"
            f"Проанализируй до {self.max_claims} самых значимых утверждений (цены, тарифы, интеграции, сроки, ограничения).\n"
            f"{rewrite_policy}\n"
            'Ответь JSON объектом: {"verdict": "pass"/"fail", "checks": [...], "rewritten_response": "...", "confidence": 0.0-1.0}\n\n'
            f"INTENT: {intent}\n"
            f"STATE: {state}\n"
            f"{history_block}"
            f"USER_MESSAGE:\n{user_message}\n\n"
            f"CANDIDATE_RESPONSE:\n{candidate_response}\n\n"
            f"KB_CONTEXT:\n{retrieved_facts}\n"
        )

    def _ensure_no_forbidden_fallback(
        self,
        response: str,
        *,
        user_message: str,
        retrieved_facts: str,
    ) -> str:
        text = str(response or "").strip()
        if not text or not self._FORBIDDEN_FALLBACK_RE.search(text):
            return text
        # Strip only the forbidden phrase, preserve the rest of the content
        stripped = self._FORBIDDEN_FALLBACK_RE.sub("", text)
        stripped = re.sub(r"\s{2,}", " ", stripped).strip(" ,.")
        if len(stripped) > 30:
            return stripped
        # Response was mostly/only forbidden fallback phrase:
        # try LLM KB rewrite first, then safe minimal response.
        llm_rewrite = self._rewrite_from_kb_llm(
            user_message=user_message,
            retrieved_facts=retrieved_facts,
            intent="",
            state="",
            dialog_history=None,
        )
        llm_rewrite = str(llm_rewrite or "").strip()
        if llm_rewrite and not self._FORBIDDEN_FALLBACK_RE.search(llm_rewrite):
            return llm_rewrite
        return self._build_safe_minimal_response(user_message=user_message)

    def _build_safe_minimal_response(self, *, user_message: str) -> str:
        query = str(user_message or "").lower()
        if re.search(r"(?:цена|стоимост|сколько|тариф|рассроч|оплат)", query):
            return (
                "Могу отвечать только по подтвержденным фактам из базы. "
                "Сейчас в контексте недостаточно данных для точного ответа по цене."
            )
        return (
            "Могу отвечать только по подтвержденным фактам из базы. "
            "Сейчас в контексте недостаточно данных для точного ответа."
        )

    def _build_kb_rewrite_prompt(
        self,
        *,
        user_message: str,
        retrieved_facts: str,
        intent: str,
        state: str,
        dialog_history: Optional[List[dict]] = None,
    ) -> str:
        history_block = ""
        if dialog_history:
            lines = []
            for entry in dialog_history[-4:]:
                user_txt = str(entry.get("user", "") or "").strip()
                bot_txt = str(entry.get("bot", "") or "").strip()
                if not user_txt and not bot_txt:
                    continue
                if user_txt:
                    lines.append(f"Клиент: {user_txt[:200]}")
                if bot_txt:
                    lines.append(f"Бот: {bot_txt[:200]}")
            if lines:
                history_block = "ИСТОРИЯ (последние ходы):\n" + "\n".join(lines) + "\n\n"

        return (
            "Ты модуль factual-rewrite для ответа менеджера.\n"
            "Сформируй финальный ответ клиенту СТРОГО по KB_CONTEXT.\n"
            "Требования:\n"
            "1) Никаких внешних знаний и выдуманных фактов.\n"
            "2) Ответ должен быть по теме USER_MESSAGE, без ухода в соседние темы.\n"
            "3) Если клиент просит полный список/все варианты/полное сравнение — покрой все релевантные пункты из KB_CONTEXT.\n"
            "4) Если в KB_CONTEXT данных недостаточно — честно скажи об ограничении, без выдумывания.\n"
            "5) Запрещены фразы про коллег/перезвон.\n"
            "6) Коротко и по делу: 1-4 предложения.\n\n"
            f"INTENT: {intent}\n"
            f"STATE: {state}\n"
            f"{history_block}"
            f"USER_MESSAGE:\n{user_message}\n\n"
            f"KB_CONTEXT:\n{retrieved_facts}\n"
        )

    def _rewrite_from_kb_llm(
        self,
        *,
        user_message: str,
        retrieved_facts: str,
        intent: str,
        state: str,
        dialog_history: Optional[List[dict]] = None,
    ) -> str:
        generate_fn = getattr(self.llm, "generate", None)
        if not callable(generate_fn):
            return ""

        prompt = self._build_kb_rewrite_prompt(
            user_message=user_message,
            retrieved_facts=retrieved_facts,
            intent=intent,
            state=state,
            dialog_history=dialog_history,
        )
        try:
            response = generate_fn(
                prompt,
                allow_fallback=False,
                purpose="factual_rewrite_from_kb",
            )
        except TypeError:
            # Test doubles may expose a simplified generate(prompt) signature.
            try:
                response = generate_fn(prompt)
            except Exception as exc:
                logger.warning("Factual KB rewrite call failed", error=str(exc))
                return ""
        except Exception as exc:
            logger.warning("Factual KB rewrite call failed", error=str(exc))
            return ""

        if isinstance(response, tuple):
            response = response[0] if response else ""
        rewritten = str(response or "").strip()
        if not rewritten:
            return ""
        cleaned = self._ensure_no_forbidden_fallback(
            rewritten,
            user_message=user_message,
            retrieved_facts=retrieved_facts,
        )
        return str(cleaned or "").strip()

    def _attempt_llm_kb_rewrite_with_verify(
        self,
        *,
        user_message: str,
        retrieved_facts: str,
        intent: str,
        state: str,
        dialog_history: Optional[List[dict]] = None,
    ) -> Optional[tuple[str, str]]:
        rewritten = self._rewrite_from_kb_llm(
            user_message=user_message,
            retrieved_facts=retrieved_facts,
            intent=intent,
            state=state,
            dialog_history=dialog_history,
        )
        if not rewritten:
            return None
        verified = self._verify_once(
            user_message=user_message,
            candidate_response=rewritten,
            retrieved_facts=retrieved_facts,
            intent=intent,
            state=state,
            allow_rewrite=False,
            dialog_history=dialog_history,
        )
        if verified is None or verified.verdict != "pass":
            return None
        return rewritten, "llm_kb_rewrite_pass"

    def _extract_terms(self, text: str) -> set[str]:
        terms = set()
        for token in self._TERM_RE.findall(str(text or "").lower()):
            if token in self._QUERY_STOP_WORDS:
                continue
            terms.add(token)
        return terms

    @classmethod
    def _grounding_facts_text(cls, retrieved_facts: str) -> str:
        facts_text = str(retrieved_facts or "").strip()
        if not facts_text:
            return ""
        if cls._EMPTY_CONTEXT_RE.match(facts_text):
            return ""
        parts = cls._QUERY_CONTEXT_SEPARATOR_RE.split(facts_text, maxsplit=1)
        query_context = str(parts[0] or "").strip()
        if len(query_context) >= 40:
            return query_context
        return facts_text

    @classmethod
    def _is_structural_line(cls, line: str) -> bool:
        value = str(line or "").strip()
        if not value:
            return True
        if cls._SECTION_HEADER_RE.fullmatch(value):
            return True
        if cls._STRUCTURAL_LINE_RE.fullmatch(value):
            return True
        return value.startswith("===") and value.endswith("===")

    def _fact_sentences(self, retrieved_facts: str) -> List[str]:
        sentences: List[str] = []
        facts_text = self._grounding_facts_text(retrieved_facts)
        chunks = re.split(r"\n+\s*---\s*\n+", facts_text)
        for chunk in chunks:
            for raw in re.split(r"(?<=[.!?])\s+|\n+", chunk):
                if self._is_structural_line(raw):
                    continue
                line = raw.strip(" \t-•*")
                if len(line) < 3:
                    continue
                if line.startswith("http://") or line.startswith("https://"):
                    continue
                if re.fullmatch(r"[\w.-]+(?:/[\w.-]+)+\.?", line):
                    continue
                if "/" in line and len(line.split()) <= 2:
                    continue
                sentences.append(line)
        return sentences

    @staticmethod
    def _normalize_sentence(sentence: str) -> str:
        text = re.sub(r"\s{2,}", " ", sentence).strip()
        if text and text[-1] not in ".!?":
            text += "."
        return text

    def _build_db_only_response(self, *, user_message: str, retrieved_facts: str) -> str:
        sentences = self._fact_sentences(retrieved_facts)
        if not sentences:
            return "В предоставленных фактах БД нет подтвержденного ответа по этому вопросу."

        query_text = str(user_message or "").lower()
        query_terms = self._extract_terms(user_message)
        wants_numeric = bool(self._HIGH_RISK_RESPONSE_RE.search(user_message or ""))
        asks_price = bool(re.search(r"(?:сколько|цена|стоимост|стоит|тариф|прайс)", query_text))
        asks_speed = bool(re.search(r"(?:как\s+быстро|сколько\s+времени|срок|за\s+сколько)", query_text))
        asks_catalog = bool(re.search(r"(?:какие\s+продукты|экосистем)", query_text))
        asks_compare = bool(re.search(r"(?:чем\s+отлич|отличают|отличия|разниц|сравн)", query_text))
        asks_composition = bool(re.search(r"(?:что\s+входит|состав|комплект|набор)", query_text))
        asks_tariff_overview = bool(
            re.search(
                r"(?:какие[^.!?\n]{0,40}тариф\w+|"
                r"тариф\w+[^.!?\n]{0,20}есть|"
                r"перечисл\w+[^.!?\n]{0,20}тариф\w+|"
                r"назов\w+[^.!?\n]{0,20}тариф\w+|"
                r"тариф\w+[^.!?\n]{0,20}сколько)",
                query_text,
            )
        )
        query_cities = set(self._CITY_RE.findall(query_text))

        if asks_tariff_overview:
            tariff_lines: List[str] = []
            seen_tariff_lines = set()
            for sentence in sentences:
                sentence_low = sentence.lower()
                mentions_tariff = bool(
                    re.search(r"(?:\bтариф\w*\b|\bmini\b|\blite\b|\bstandard\b|\bpro\b)", sentence_low)
                )
                has_numeric_or_price = bool(
                    re.search(r"(?:₸|тенге|тг|стоим|цена|\d)", sentence_low)
                )
                if not mentions_tariff or not has_numeric_or_price:
                    continue
                normalized = self._normalize_sentence(sentence)
                key = normalized.lower()
                if key in seen_tariff_lines:
                    continue
                seen_tariff_lines.add(key)
                tariff_lines.append(normalized)
            if tariff_lines:
                return " ".join(tariff_lines[:6])

        sentence_terms: List[set[str]] = []
        term_df: Counter[str] = Counter()
        for sentence in sentences:
            sent_terms = self._extract_terms(sentence)
            sentence_terms.append(sent_terms)
            for term in (query_terms & sent_terms):
                term_df[term] += 1

        scored = []
        seen = set()
        for idx, sentence in enumerate(sentences):
            key = sentence.lower()
            if key in seen:
                continue
            seen.add(key)
            sent_terms = sentence_terms[idx]
            overlap_terms = query_terms & sent_terms
            overlap = len(overlap_terms) if query_terms else 0
            rarity_bonus = sum(1.0 / term_df[t] for t in overlap_terms if term_df[t] > 0)

            sentence_low = sentence.lower()
            has_price_marker = bool(
                re.search(r"(?:₸|тенге|тг|стоим|цена|тариф|/\s*(?:год|мес|месяц))", sentence_low)
            )
            has_time_marker = bool(
                re.search(r"(?:дн(?:я|ей)?|час(?:а|ов)?|срок|удал[её]нн|эцп|в\s+тот\s+же\s+день)", sentence_low)
            )
            has_numeric = bool(re.search(r"\d", sentence))
            has_day_range = bool(
                re.search(r"\b\d+\s*(?:[-–]\s*\d+)(?:\s+\w+){0,2}\s*дн(?:я|ей)?\b", sentence_low)
            )
            has_workday = "рабоч" in sentence_low

            numeric_bonus = 1 if wants_numeric and has_numeric else 0
            price_bonus = 0
            if asks_price:
                if has_price_marker:
                    price_bonus += 4
                elif has_time_marker:
                    price_bonus -= 2
            speed_bonus = 3 if asks_speed and has_time_marker else 0
            if asks_speed and has_day_range:
                speed_bonus += 2
            if asks_speed and has_workday:
                speed_bonus += 1
            if asks_speed and has_price_marker and not has_time_marker:
                speed_bonus -= 3

            city_bonus = 0
            if asks_speed and query_cities:
                sentence_cities = set(self._CITY_RE.findall(sentence_low))
                if sentence_cities & query_cities:
                    city_bonus += 4
                elif sentence_cities:
                    city_bonus -= 4

            structure_bonus = 0
            if asks_compare and (has_numeric or "—" in sentence or ":" in sentence):
                structure_bonus += 2
            if asks_composition and ("," in sentence or ":" in sentence):
                structure_bonus += 2

            compact_bonus = 1 if 5 <= len(sentence.split()) <= 28 else 0
            generic_penalty = 0
            if self._ABSTRACT_SENTENCE_RE.search(sentence_low) and not has_numeric:
                generic_penalty += 3
            if len(sent_terms) <= 3 and not has_numeric:
                generic_penalty += 2
            score = (
                overlap * 3
                + rarity_bonus * 2
                + numeric_bonus
                + price_bonus
                + speed_bonus
                + city_bonus
                + structure_bonus
                + compact_bonus
                - generic_penalty
            )
            scored.append((score, idx, sentence))

        scored.sort(key=lambda item: (-item[0], item[1]))
        pick_count = 3 if (
            asks_price
            or asks_catalog
            or asks_compare
            or asks_composition
            or asks_tariff_overview
        ) else 2
        picked = [item[2] for item in scored[:pick_count]] or sentences[:pick_count]

        if asks_price and picked:
            if not any(re.search(r"(?:₸|тенге|тг|стоим|цена|тариф)", s, re.IGNORECASE) for s in picked):
                for _, _, sentence in scored:
                    if re.search(r"(?:₸|тенге|тг|стоим|цена|тариф)", sentence, re.IGNORECASE):
                        picked = [sentence] + [s for s in picked if s != sentence]
                        picked = picked[:pick_count]
                        break

        response = " ".join(self._normalize_sentence(sentence) for sentence in picked).strip()
        response = self._FORBIDDEN_FALLBACK_RE.sub("", response)
        response = re.sub(r"\s{2,}", " ", response).strip(" ,.;")
        if not response:
            return "В предоставленных фактах БД нет подтвержденного ответа по этому вопросу."
        return self._normalize_sentence(response)


__all__ = [
    "ClaimCheck",
    "VerifierOutput",
    "VerificationResult",
    "FactualVerifier",
]
