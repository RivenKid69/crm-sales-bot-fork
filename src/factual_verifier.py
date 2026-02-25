"""
Same-model factual verifier for autonomous responses.

Runs an isolated verification pass against retrieved KB facts using the same LLM
via structured output. If the candidate response is not grounded, it rewrites
the answer to a DB-grounded variant without handoff/fallback phrases.
"""

from __future__ import annotations

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
    verdict: Literal["pass", "fail"] = "fail"
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
            return VerificationResult(
                final_response=self._build_db_only_response(
                    user_message=user_message,
                    retrieved_facts=facts_text,
                ),
                changed=True,
                verifier_used=True,
                verifier_verdict="error",
                reason_codes=["llm_error", "db_only_rewrite"],
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

        # Change 3: use rewritten_response from pass 1 as fallback before db_only
        # rewritten is LLM-generated with KB context — better than 2 raw sentences
        if rewritten:
            cleaned_fallback = self._ensure_no_forbidden_fallback(
                rewritten,
                user_message=user_message,
                retrieved_facts=facts_text,
            )
            if len(cleaned_fallback) > 30:
                reason_codes.append("pass1_rewrite_fallback")
                return VerificationResult(
                    final_response=cleaned_fallback,
                    changed=(cleaned_fallback != original),
                    verifier_used=True,
                    verifier_verdict="fail",
                    reason_codes=reason_codes,
                    fallback_required=False,
                )

        db_only_response = self._build_db_only_response(
            user_message=user_message,
            retrieved_facts=facts_text,
        )
        reason_codes.append("db_only_rewrite")
        return VerificationResult(
            final_response=db_only_response,
            changed=(db_only_response != original),
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
            "  НЕ ПРОВЕРЯТЬ: разговорные конструкции, оценки, переходы, риторические фразы\n"
            "  (например: «отлично подойдёт», «хороший выбор», «давайте разберёмся», «для вашего формата»).\n"
            "  Это не фактические утверждения — игнорировать при проверке claims.\n"
            f"Проанализируй до {self.max_claims} самых значимых утверждений (цены, тарифы, интеграции, сроки, ограничения).\n"
            f"{rewrite_policy}\n"
            "Ответ должен быть в JSON по схеме.\n\n"
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
        # Response was only the forbidden phrase — use DB safety net
        return self._build_db_only_response(
            user_message=user_message,
            retrieved_facts=retrieved_facts,
        )

    def _extract_terms(self, text: str) -> set[str]:
        terms = set()
        for token in self._TERM_RE.findall(str(text or "").lower()):
            if token in self._QUERY_STOP_WORDS:
                continue
            terms.add(token)
        return terms

    def _fact_sentences(self, retrieved_facts: str) -> List[str]:
        sentences: List[str] = []
        chunks = re.split(r"\n+\s*---\s*\n+", str(retrieved_facts or ""))
        for chunk in chunks:
            for raw in re.split(r"(?<=[.!?])\s+|\n+", chunk):
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

        query_terms = self._extract_terms(user_message)
        wants_numeric = bool(self._HIGH_RISK_RESPONSE_RE.search(user_message or ""))

        scored = []
        seen = set()
        for idx, sentence in enumerate(sentences):
            key = sentence.lower()
            if key in seen:
                continue
            seen.add(key)
            sent_terms = self._extract_terms(sentence)
            overlap = len(query_terms & sent_terms) if query_terms else 0
            numeric_bonus = 2 if wants_numeric and self._HIGH_RISK_RESPONSE_RE.search(sentence) else 0
            compact_bonus = 1 if 5 <= len(sentence.split()) <= 28 else 0
            score = overlap * 3 + numeric_bonus + compact_bonus
            scored.append((score, idx, sentence))

        scored.sort(key=lambda item: (-item[0], item[1]))
        picked = [item[2] for item in scored[:2]] or sentences[:2]

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
