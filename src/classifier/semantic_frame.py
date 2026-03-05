"""
Semantic frame extraction for additive intent understanding.

This module does NOT replace primary intent classification.
It adds structured semantic metadata over the current intent:
- asked_dimensions: what user is asking about (product_fit/pricing/etc.)
- request flags: pricing/comparison/direct answer
- basic entities extracted from user message
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Protocol, Sequence, Set

from pydantic import BaseModel, Field

from src.logger import logger


class StructuredLLMProtocol(Protocol):
    """Minimal protocol needed from LLM client."""

    def generate_structured(
        self,
        prompt: str,
        schema: Any,
        allow_fallback: bool = True,
        return_trace: bool = False,
        purpose: str = "structured_generation",
        temperature: float = 0.05,
        num_predict: int = 2048,
    ) -> Optional[Any]:
        ...


class SemanticEntities(BaseModel):
    """Extracted numeric/business entities from user message."""

    store_count: Optional[int] = None
    employee_count: Optional[int] = None
    business_type: str = ""


class SemanticFrameModel(BaseModel):
    """Structured semantic frame returned by LLM."""

    primary_goal: str = "unknown"
    asked_dimensions: List[str] = Field(default_factory=list)
    needs_direct_answer: bool = False
    has_question: bool = False
    price_requested: bool = False
    comparison_requested: bool = False
    recommended_intent: str = ""
    recommended_confidence: float = 0.0
    override_intent: bool = False
    confidence: float = 0.0
    entities: SemanticEntities = Field(default_factory=SemanticEntities)


class SemanticFrameExtractor:
    """Additive semantic-frame extractor on top of primary intent."""

    _ALLOWED_DIMENSIONS: Set[str] = {
        "product_fit",
        "pricing",
        "integrations",
        "features",
        "equipment",
        "security",
        "support",
        "comparison",
        "implementation",
        "delivery",
        "contact",
        "demo",
    }

    _QUESTION_RE = re.compile(
        r"(?:\?|(?:^|\s)(?:что|как|какой|какие|сколько|где|когда|почему|можно\s+ли|есть\s+ли)(?:\s|$))",
        re.IGNORECASE,
    )
    _PRICE_RE = re.compile(
        r"(?:\bцена\w*|\bстоимост\w*|\bсколько\s+стоит|\bтариф\w*|\bпоч[её]м|\bрассроч\w*)",
        re.IGNORECASE,
    )
    _COMPARE_RE = re.compile(
        r"(?:\bсравн\w*|\bчем\s+лучше\b|\bчем\s+отлич\w*|\bvs\b|\bконкурент\w*)",
        re.IGNORECASE,
    )
    _PRODUCT_FIT_RE = re.compile(
        r"(?:какие?\s+(?:ваши\s+)?(?:продукт\w+|решени\w+)\s+(?:мне\s+)?(?:подойдут|подходит)"
        r"|что\s+(?:мне\s+)?(?:подойдет|подойд[её]т)"
        r"|посовет\w+\s+(?:мне\s+)?(?:продукт|решени\w+)"
        r"|какой\s+(?:вариант|продукт|тариф)\s+лучше)",
        re.IGNORECASE,
    )
    _INTEGRATION_RE = re.compile(
        r"(?:интеграц\w*|api\b|webhook|kaspi|каспи|1с\b|bitrix|amo|маркетплейс)",
        re.IGNORECASE,
    )
    _FEATURE_RE = re.compile(
        r"(?:функци\w*|возможност\w*|умеет|как\s+работает|что\s+может)",
        re.IGNORECASE,
    )
    _EQUIPMENT_RE = re.compile(
        r"(?:оборудовани\w*|моноблок|pos\b|принтер|сканер|вес\w*|терминал)",
        re.IGNORECASE,
    )
    _SECURITY_RE = re.compile(
        r"(?:безопасн\w*|шифрован\w*|ssl\b|tls\b|сертификат\w*)",
        re.IGNORECASE,
    )
    _SUPPORT_RE = re.compile(
        r"(?:поддержк\w*|обучени\w*|внедрени\w*|настро\w*|сопровожден\w*)",
        re.IGNORECASE,
    )
    _DELIVERY_RE = re.compile(
        r"(?:доставк\w*|курьер|логист\w*|самовывоз)",
        re.IGNORECASE,
    )
    _DEMO_RE = re.compile(
        r"(?:демо|тестов\w+\s+период|пробн\w+\s+период|попробовать)",
        re.IGNORECASE,
    )
    _CONTACT_RE = re.compile(
        r"(?:связаться|перезвон\w*|контакт\w*|номер|телефон|почта|email)",
        re.IGNORECASE,
    )
    _STORE_RE = re.compile(r"(\d+)\s*(?:точ\w+|филиал\w*|магазин\w*)", re.IGNORECASE)
    _EMPLOYEE_RE = re.compile(
        r"(\d+)\s*(?:человек\w*|сотрудник\w*|менеджер\w*|продавц\w*)", re.IGNORECASE
    )
    _BIZ_RE = re.compile(
        r"(?:продуктов\w+\s+магазин|магазин|кафе|ресторан|аптека|салон|клиника|отель)",
        re.IGNORECASE,
    )

    def __init__(self, llm: StructuredLLMProtocol):
        self.llm = llm
        self._known_intents = self._load_known_intents()

    @staticmethod
    def _load_known_intents() -> Set[str]:
        """Load known intent names from taxonomy examples (SSoT fallback-safe)."""
        try:
            from src.classifier.intents.examples import get_all_intents

            intents = {str(i).strip() for i in get_all_intents() if i}
            if intents:
                return intents
        except Exception:
            pass
        # Safe fallback if taxonomy loader fails.
        return {"unclear", "greeting", "small_talk", "agreement", "price_question", "question_features"}

    def extract(
        self,
        *,
        message: str,
        primary_intent: str,
        secondary_signals: Optional[Sequence[str]] = None,
        candidate_intents: Optional[Sequence[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Extract semantic frame with LLM; fallback to deterministic heuristics."""
        base = self._heuristic_frame(
            message=message,
            primary_intent=primary_intent,
            secondary_signals=secondary_signals or [],
        )
        prompt = self._build_prompt(
            message=message,
            primary_intent=primary_intent,
            secondary_signals=list(secondary_signals or []),
            candidate_intents=list(candidate_intents or []),
            context=context or {},
        )
        try:
            llm_result = self.llm.generate_structured(
                prompt=prompt,
                schema=SemanticFrameModel,
                allow_fallback=False,
                purpose="semantic_frame_extraction",
                temperature=0.0,
                num_predict=512,
            )
        except Exception as exc:
            logger.warning("Semantic frame LLM call failed, fallback to heuristics", error=str(exc))
            llm_result = None

        if llm_result is None:
            base["source"] = "heuristic"
            base.pop("base_intent", None)
            return base

        try:
            parsed = llm_result.model_dump() if hasattr(llm_result, "model_dump") else dict(llm_result)
        except Exception:
            parsed = base

        merged = self._merge_frames(base, parsed)
        merged["source"] = "llm"
        merged.pop("base_intent", None)
        return merged

    def _build_prompt(
        self,
        *,
        message: str,
        primary_intent: str,
        secondary_signals: List[str],
        candidate_intents: List[str],
        context: Dict[str, Any],
    ) -> str:
        state = str(context.get("state", "") or "")
        spin_phase = str(context.get("spin_phase", "") or "")
        last_action = str(context.get("last_action", "") or "")
        last_intent = str(context.get("last_intent", "") or "")
        intent_history = context.get("intent_history", [])
        if not isinstance(intent_history, list):
            intent_history = []
        recent_intents = [str(i) for i in intent_history[-4:] if i]
        compact_candidates = [str(i).strip() for i in candidate_intents if i]
        if primary_intent and primary_intent not in compact_candidates:
            compact_candidates.insert(0, primary_intent)
        compact_candidates = compact_candidates[:8]
        return (
            "Ты извлекаешь semantic frame из сообщения клиента.\n"
            "Верни JSON строго по схеме.\n"
            "Правила:\n"
            "1) asked_dimensions выбирай ТОЛЬКО из: "
            "product_fit, pricing, integrations, features, equipment, security, support, "
            "comparison, implementation, delivery, contact, demo.\n"
            "2) Если клиент не просит цену напрямую, price_requested=false.\n"
            "3) Для запросов подбора решения (какой продукт/что подойдет) добавляй product_fit.\n"
            "4) needs_direct_answer=true для прямых вопросов.\n"
            "5) recommended_intent выбирай из существующей таксономии интентов Wipon. "
            "Если нет уверенности, оставь primary_intent.\n"
            "6) override_intent=true ТОЛЬКО если текущий primary_intent явно хуже по смыслу.\n"
            "7) confidence и recommended_confidence от 0 до 1.\n\n"
            f"Текущее сообщение клиента: {message}\n"
            f"Primary intent: {primary_intent}\n"
            f"Secondary signals: {secondary_signals}\n"
            f"Intent candidates (подсказка): {compact_candidates}\n"
            f"Recent intent history: {recent_intents}\n"
            f"Context state={state}, spin_phase={spin_phase}, last_action={last_action}, last_intent={last_intent}\n"
        )

    def _heuristic_frame(
        self,
        *,
        message: str,
        primary_intent: str,
        secondary_signals: Sequence[str],
    ) -> Dict[str, Any]:
        text = str(message or "")
        low = text.lower()

        asked: Set[str] = set()
        if self._PRODUCT_FIT_RE.search(text):
            asked.add("product_fit")
        if self._PRICE_RE.search(text):
            asked.add("pricing")
        if self._INTEGRATION_RE.search(text):
            asked.add("integrations")
        if self._FEATURE_RE.search(text):
            asked.add("features")
        if self._EQUIPMENT_RE.search(text):
            asked.add("equipment")
        if self._SECURITY_RE.search(text):
            asked.add("security")
        if self._SUPPORT_RE.search(text):
            asked.add("support")
        if self._COMPARE_RE.search(text):
            asked.add("comparison")
        if self._DELIVERY_RE.search(text):
            asked.add("delivery")
        if self._DEMO_RE.search(text):
            asked.add("demo")
        if self._CONTACT_RE.search(text):
            asked.add("contact")

        intent_low = str(primary_intent or "").lower()
        if intent_low.startswith("question_integr"):
            asked.add("integrations")
        if intent_low.startswith("question_feature"):
            asked.add("features")
        if intent_low.startswith(("price_", "pricing_", "cost_")):
            asked.add("pricing")
        if intent_low in {"comparison", "pricing_comparison", "question_tariff_comparison"}:
            asked.add("comparison")
        if intent_low in {"demo_request"}:
            asked.add("demo")
        if intent_low in {"callback_request", "consultation_request", "contact_provided"}:
            asked.add("contact")

        for signal in secondary_signals:
            signal_low = str(signal).lower()
            if signal_low.startswith("question_integr"):
                asked.add("integrations")
            elif signal_low.startswith("question_feature"):
                asked.add("features")
            elif signal_low.startswith(("price_", "pricing_", "cost_")) or signal_low == "price_question":
                asked.add("pricing")
            elif signal_low in {"comparison", "pricing_comparison", "question_tariff_comparison"}:
                asked.add("comparison")

        has_question = bool(self._QUESTION_RE.search(low))
        price_requested = "pricing" in asked
        comparison_requested = "comparison" in asked
        needs_direct_answer = has_question or bool(
            intent_low.startswith(("question_", "price_", "pricing_", "comparison", "cost_", "roi_"))
        )

        primary_goal = "discover"
        if "product_fit" in asked:
            primary_goal = "recommend_solution"
        elif price_requested:
            primary_goal = "quote_price"
        elif "comparison" in asked:
            primary_goal = "compare_options"
        elif any(x in asked for x in ("integrations", "features", "equipment", "security", "support")):
            primary_goal = "answer_question"
        elif "contact" in asked:
            primary_goal = "arrange_contact"
        elif "demo" in asked:
            primary_goal = "offer_trial"

        entities: Dict[str, Any] = {
            "store_count": self._extract_int(self._STORE_RE, text),
            "employee_count": self._extract_int(self._EMPLOYEE_RE, text),
            "business_type": self._extract_business_type(text),
        }
        if entities["store_count"] is None and "точк" in low:
            entities["store_count"] = self._extract_loose_number_before_word(low, "точ")

        frame = {
            "base_intent": primary_intent,
            "primary_goal": primary_goal,
            "asked_dimensions": sorted(d for d in asked if d in self._ALLOWED_DIMENSIONS),
            "needs_direct_answer": needs_direct_answer,
            "has_question": has_question,
            "price_requested": price_requested,
            "comparison_requested": comparison_requested,
            "recommended_intent": primary_intent,
            "recommended_confidence": 0.0,
            "override_intent": False,
            "confidence": 0.62,
            "entities": entities,
        }
        inferred_intent, inferred_conf = self._infer_recommended_intent(frame, primary_intent)
        if inferred_conf > 0.0:
            frame["recommended_intent"] = inferred_intent
            frame["recommended_confidence"] = inferred_conf
            frame["override_intent"] = inferred_intent != primary_intent
        return frame

    def _merge_frames(self, heuristic: Dict[str, Any], llm_frame: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(heuristic)
        llm_dims = llm_frame.get("asked_dimensions", [])
        if isinstance(llm_dims, list) and llm_dims:
            merged["asked_dimensions"] = sorted(
                d for d in {str(x).strip().lower() for x in llm_dims if x} if d in self._ALLOWED_DIMENSIONS
            )

        llm_primary_goal = str(llm_frame.get("primary_goal", "") or "").strip().lower()
        if llm_primary_goal and llm_primary_goal != "unknown":
            merged["primary_goal"] = llm_primary_goal

        llm_recommended_intent = str(llm_frame.get("recommended_intent", "") or "").strip()
        if llm_recommended_intent:
            merged["recommended_intent"] = llm_recommended_intent

        for key in ("needs_direct_answer", "has_question", "price_requested", "comparison_requested"):
            if key in llm_frame:
                merged[key] = bool(merged.get(key)) or bool(llm_frame.get(key))

        if "override_intent" in llm_frame:
            merged["override_intent"] = bool(merged.get("override_intent")) or bool(llm_frame.get("override_intent"))

        llm_conf = llm_frame.get("confidence")
        if isinstance(llm_conf, (int, float)):
            merged["confidence"] = max(0.0, min(float(llm_conf), 1.0))
        rec_conf = llm_frame.get("recommended_confidence")
        if isinstance(rec_conf, (int, float)):
            merged["recommended_confidence"] = max(0.0, min(float(rec_conf), 1.0))

        llm_entities = llm_frame.get("entities", {})
        if isinstance(llm_entities, dict):
            entities = dict(merged.get("entities", {}))
            for field in ("store_count", "employee_count", "business_type"):
                val = llm_entities.get(field)
                if val is not None and val != "":
                    entities[field] = val
            merged["entities"] = entities

        if "pricing" in set(merged.get("asked_dimensions", [])):
            merged["price_requested"] = True
        if "comparison" in set(merged.get("asked_dimensions", [])):
            merged["comparison_requested"] = True

        base_intent = str(
            heuristic.get("base_intent")
            or heuristic.get("recommended_intent")
            or ""
        ).strip()
        recommended_intent = str(merged.get("recommended_intent") or "").strip()
        if not recommended_intent or recommended_intent not in self._known_intents:
            recommended_intent = base_intent
        merged["recommended_intent"] = recommended_intent

        if not isinstance(merged.get("override_intent"), bool):
            merged["override_intent"] = False
        if recommended_intent == base_intent:
            merged["override_intent"] = False

        # Deterministic fallback: if LLM didn't provide intent recommendation,
        # infer from semantic frame dimensions/question flags.
        rec_conf = float(merged.get("recommended_confidence", 0.0) or 0.0)
        if rec_conf <= 0.0:
            inferred_intent, inferred_conf = self._infer_recommended_intent(merged, base_intent)
            if inferred_intent and inferred_intent in self._known_intents:
                merged["recommended_intent"] = inferred_intent
                merged["recommended_confidence"] = inferred_conf
                merged["override_intent"] = inferred_intent != base_intent
            else:
                merged["recommended_intent"] = base_intent
                merged["recommended_confidence"] = 0.0
                merged["override_intent"] = False

        return merged

    def _infer_recommended_intent(self, frame: Dict[str, Any], base_intent: str) -> tuple[str, float]:
        """Infer recommended intent from normalized semantic frame when LLM is silent."""
        dims = {str(d).strip().lower() for d in (frame.get("asked_dimensions") or []) if d}
        has_question = bool(frame.get("has_question")) or bool(frame.get("needs_direct_answer"))
        if not dims or not has_question:
            return base_intent, 0.0

        inferred = base_intent
        confidence = 0.0

        if "pricing" in dims:
            inferred = "price_question"
            confidence = 0.90
        elif "comparison" in dims:
            inferred = "comparison"
            confidence = 0.88
        elif "integrations" in dims:
            inferred = "question_integrations"
            confidence = 0.86
        elif "security" in dims:
            inferred = "question_security"
            confidence = 0.85
        elif "equipment" in dims:
            inferred = "question_equipment_general"
            confidence = 0.84
        elif dims & {"features", "support", "implementation", "delivery"}:
            inferred = "question_features"
            confidence = 0.83
        elif "product_fit" in dims:
            inferred = "question_features"
            confidence = 0.86

        return inferred, confidence

    @staticmethod
    def _extract_int(pattern: re.Pattern, text: str) -> Optional[int]:
        m = pattern.search(text or "")
        if not m:
            return None
        try:
            return int(m.group(1))
        except Exception:
            return None

    @classmethod
    def _extract_business_type(cls, text: str) -> str:
        m = cls._BIZ_RE.search(text or "")
        return m.group(0).lower().strip() if m else ""

    @staticmethod
    def _extract_loose_number_before_word(text: str, stem: str) -> Optional[int]:
        m = re.search(rf"(\d+)\s*\w*{re.escape(stem)}\w*", text or "", re.IGNORECASE)
        if not m:
            return None
        try:
            return int(m.group(1))
        except Exception:
            return None
