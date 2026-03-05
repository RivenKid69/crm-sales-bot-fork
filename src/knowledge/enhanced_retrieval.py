"""
Enhanced retrieval pipeline for autonomous flow.

Combines:
- follow-up query rewriting,
- complexity detection + query decomposition,
- multi-query retrieval with reciprocal-rank fusion (RRF),
- long-context zigzag reordering,
- state-context backfill within a shared KB character budget.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Protocol, Sequence, Set, Tuple, Type, TypeVar

from pydantic import BaseModel, Field

from src.logger import logger
from src.settings import settings

from .autonomous_kb import MAX_KB_CHARS, load_facts_for_state
from .category_router import CategoryRouter
from .reranker import get_reranker
from .retriever import SKIP_RETRIEVAL_INTENTS, SearchResult, get_retriever

T = TypeVar("T", bound=BaseModel)

# Strip KB editor-only annotations before sending facts to LLM.
# "⚠️ НЕ ПУТАТЬ: ..." lines are metadata for KB editors, not for the LLM.
_KB_META_STRIP_RE = re.compile(
    r"(?m)^\s*(?:•\s*)?⚠️\s*НЕ\s+ПУТАТЬ:[^\n]*\n?",
)


class LLMProtocol(Protocol):
    def generate(self, prompt: str, **kwargs: Any) -> str:
        ...


class StructuredLLMProtocol(LLMProtocol, Protocol):
    def generate_structured(self, prompt: str, schema: Type[T]) -> Optional[T]:
        ...


class SubQuery(BaseModel):
    query: str = Field(min_length=1)
    categories: List[str] = Field(default_factory=list)


class DecompositionResult(BaseModel):
    is_complex: bool = False
    sub_queries: List[SubQuery] = Field(default_factory=list)


class QueryRewriter:
    """Rewrites follow-up questions into standalone retrieval queries."""

    _STOP_WORDS = frozenset({
        "и", "в", "на", "с", "по", "а", "но", "что", "как", "это",
        "не", "да", "ну", "же", "ли", "бы", "у", "к", "о", "из", "за",
        "то", "мы", "вы", "он", "она", "они", "я", "мне", "для",
    })
    _FOLLOW_UP_PRONOUN_RE = re.compile(
        r"\b(?:это|они|такой|туда|там|его|её|ее)\b",
        re.IGNORECASE,
    )
    _PREFIX_RE = re.compile(
        r"^(?:переписанный запрос|самостоятельный запрос|запрос)[:\-\s]+",
        re.IGNORECASE,
    )
    _SELECTION_RE = re.compile(
        r"^\s*(?:"
        r"(?P<num>[1-3])"
        r"|(?P<ord>перв(?:ый|ое|ую|ая)|втор(?:ой|ое|ую|ая)|трет(?:ий|ье|ью|ья))"
        r")\s*(?:вариант|пункт)?\s*$",
        re.IGNORECASE,
    )
    _NUMBERED_OPTION_RE = re.compile(r"^\s*([1-3])[\)\.\-]\s*(.+?)\s*$", re.MULTILINE)
    _FACT_DISAMBIG_PROMPT_RE = re.compile(
        r"уточните,\s*пожалуйста,\s*что\s+вы\s+имеете\s+в\s+виду",
        re.IGNORECASE,
    )
    _OPTION_HINT_PATTERNS: Tuple[Tuple[str, re.Pattern], ...] = (
        ("module", re.compile(r"(?:модул|укм|маркиров|акциз|алкогол)", re.IGNORECASE)),
        ("kit", re.compile(r"(?:комплект|оборудован|моноблок|сканер|принтер|кассов)", re.IGNORECASE)),
        ("tariff", re.compile(r"(?:тариф|подписк|в\s+год|за\s+год)", re.IGNORECASE)),
    )

    def __init__(self, llm: LLMProtocol, rewrite_min_words: int = 4):
        self.llm = llm
        self.rewrite_min_words = max(1, rewrite_min_words)

    def should_rewrite(self, user_message: str) -> bool:
        text = (user_message or "").strip()
        if not text:
            return False
        if self._FOLLOW_UP_PRONOUN_RE.search(text):
            return True
        return self._word_count(text) < self.rewrite_min_words

    def rewrite(self, user_message: str, history: Optional[List[Dict[str, Any]]] = None) -> str:
        original = (user_message or "").strip()
        if not original:
            return ""

        history = history or []
        deterministic = self.resolve_fact_disambiguation_selection(
            user_message=original,
            history=history,
        )
        if deterministic:
            return deterministic

        if not self.should_rewrite(original):
            return original

        if not history:
            # Without context we cannot safely resolve references.
            return original

        prompt = (
            "Перепиши вопрос клиента как самостоятельный поисковый запрос.\n"
            "Диалог:\n"
            f"{self._format_last_turns(history)}\n"
            f"Вопрос клиента: {original}\n"
            "Самостоятельный запрос:"
        )

        try:
            rewritten = self.llm.generate(prompt, allow_fallback=False)
        except TypeError:
            # Compatibility with minimal test doubles that do not accept kwargs.
            rewritten = self.llm.generate(prompt)
        except Exception as e:
            logger.warning("Query rewrite failed, using original query", error=str(e))
            return original

        cleaned = self._clean_rewrite(rewritten)
        if not cleaned:
            return original

        # Safety: reject rewrites that dropped most key terms from the original query.
        orig_words = self._lexical_terms(original) - self._STOP_WORDS
        rew_words = self._lexical_terms(cleaned) - self._STOP_WORDS
        overlap = len(orig_words & rew_words) / len(orig_words) if orig_words else 1.0
        # Short numeric/ordinal answers ("2", "второй") and terse follow-ups are valid
        # rewrite targets with naturally low lexical overlap.
        if len(orig_words) >= 3 and overlap < 0.2:
            logger.warning(
                "QueryRewriter diverged, using original",
                original=original,
                rewritten=cleaned,
            )
            return original
        return cleaned

    def resolve_fact_disambiguation_selection(
        self,
        *,
        user_message: str,
        history: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> Optional[str]:
        return self._rewrite_fact_disambiguation_selection(
            answer=(user_message or "").strip(),
            history=history or [],
        )

    def _rewrite_fact_disambiguation_selection(
        self,
        *,
        answer: str,
        history: Sequence[Dict[str, Any]],
    ) -> Optional[str]:
        if not history:
            return None

        for turn in reversed(list(history)):
            bot_text = str((turn or {}).get("bot", "") or "")
            user_text = str((turn or {}).get("user", "") or "").strip()
            if not bot_text or not user_text:
                continue
            if not self._FACT_DISAMBIG_PROMPT_RE.search(bot_text):
                break  # last bot turn was not a disambiguation → nothing to resolve

            options = self._extract_numbered_options(bot_text)
            if not options:
                continue
            selection_index = self._selection_index(answer)
            if selection_index is None:
                selection_index = self._semantic_option_index(answer, options)
            if selection_index is None:
                continue
            if selection_index >= len(options):
                continue

            selected = options[selection_index]
            rewritten = f"{user_text}. Уточнение клиента: {selected}."
            logger.info(
                "fact_disambiguation_selection_resolved",
                selected_option=selected,
                base_query=user_text[:160],
            )
            return rewritten

        return None

    @classmethod
    def _selection_index(cls, answer: str) -> Optional[int]:
        text = (answer or "").strip().lower()
        if not text:
            return None
        match = cls._SELECTION_RE.match(text)
        if not match:
            return None
        num = match.group("num")
        if num is not None:
            idx = int(num) - 1
            if 0 <= idx <= 2:
                return idx
            return None
        ordinal = str(match.group("ord") or "").lower()
        if ordinal.startswith("перв"):
            return 0
        if ordinal.startswith("втор"):
            return 1
        if ordinal.startswith("трет"):
            return 2
        return None

    @classmethod
    def _extract_numbered_options(cls, bot_text: str) -> List[str]:
        options: List[str] = []
        for match in cls._NUMBERED_OPTION_RE.finditer(bot_text or ""):
            options.append(match.group(2).strip())
        return options

    @classmethod
    def _semantic_option_index(cls, answer: str, options: Sequence[str]) -> Optional[int]:
        text = str(answer or "").strip()
        if len(text) < 3:
            return None

        matches: List[int] = []
        for idx, option in enumerate(options):
            option_text = str(option or "").lower()
            option_type: Optional[str] = None
            if "модул" in option_text or "укм" in option_text:
                option_type = "module"
            elif "комплект" in option_text or "оборуд" in option_text:
                option_type = "kit"
            elif "тариф" in option_text:
                option_type = "tariff"
            if not option_type:
                continue
            for typ, pattern in cls._OPTION_HINT_PATTERNS:
                if typ != option_type:
                    continue
                if pattern.search(text):
                    matches.append(idx)
                    break

        unique = sorted(set(matches))
        if len(unique) == 1:
            return unique[0]
        return None

    def _format_last_turns(self, history: List[Dict[str, Any]]) -> str:
        lines: List[str] = []
        for turn in history[-3:]:
            user = (turn.get("user") or "").strip()
            bot = (turn.get("bot") or "").strip()
            if user:
                lines.append(f"Клиент: {user}")
            if bot:
                lines.append(f"Бот: {bot}")
        return "\n".join(lines) if lines else "(история пуста)"

    def _clean_rewrite(self, rewritten: Any) -> str:
        if rewritten is None:
            return ""
        if isinstance(rewritten, tuple):
            rewritten = rewritten[0]
        text = str(rewritten).strip()
        if not text:
            return ""
        first_line = text.split("\n", 1)[0].strip()
        return self._PREFIX_RE.sub("", first_line).strip()

    @staticmethod
    def _word_count(text: str) -> int:
        return len(re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", text))

    @staticmethod
    def _lexical_terms(text: str) -> Set[str]:
        return set(re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", str(text or "").lower()))


class ComplexityDetector:
    """Rule-based complexity detection without LLM calls."""

    STRONG_MARKERS = (" сравн", " vs ", " против ", " отлич")
    STRONG_COMPARE_MARKERS = (
        "что лучше", "чем лучше", "чем отличается", "плюсы", "минусы", "альтернатива",
    )
    STRONG_LOGIC_MARKERS = (
        "как связано", "в чем связь", "как влияет", "зависит ли", "почему", "за счет чего",
    )
    WEAK_MARKERS = (" и ", " а также ", " или ", " ещё ", " плюс ")
    COMPLEX_PATTERNS = (
        re.compile(r"как.*и.*сколько", re.IGNORECASE | re.DOTALL),
        re.compile(r"что.*и.*как", re.IGNORECASE | re.DOTALL),
        re.compile(r"сколько.*и.*как", re.IGNORECASE | re.DOTALL),
    )

    def __init__(self, min_complexity_length: int = 30):
        self.min_complexity_length = max(1, min_complexity_length)

    def is_complex(self, query: str) -> bool:
        text = (query or "").strip()
        if not text:
            return False

        length = len(text)
        lowered = f" {text.lower()} "

        if text.count("?") >= 2:
            return True

        if length > self.min_complexity_length:
            if any(marker in lowered for marker in self.STRONG_MARKERS):
                return True
            if any(marker in lowered for marker in self.STRONG_COMPARE_MARKERS):
                return True
            # "если ... то ..." is usually a logical relation query needing multi-fact retrieval.
            if "если" in lowered and " то " in lowered:
                return True
            if any(marker in lowered for marker in self.STRONG_LOGIC_MARKERS):
                return True

        weak_hits = sum(lowered.count(marker) for marker in self.WEAK_MARKERS)
        if (weak_hits >= 2 and length > 50) or (weak_hits >= 1 and length > 80):
            return True

        if length > 80 and text.count(",") >= 2:
            return True

        return any(pattern.search(text) for pattern in self.COMPLEX_PATTERNS)


class QueryDecomposer:
    """LLM-based decomposition for complex retrieval queries."""

    def __init__(self, llm: StructuredLLMProtocol, max_sub_queries: int = 4):
        self.llm = llm
        self.max_sub_queries = max(1, max_sub_queries)

    def decompose(self, query: str) -> Optional[DecompositionResult]:
        query = (query or "").strip()
        if not query:
            return None
        if not hasattr(self.llm, "generate_structured"):
            return None

        categories = ", ".join(CategoryRouter.CATEGORIES)
        prompt = (
            "Разбей клиентский запрос на подзапросы для поиска в базе знаний.\n"
            "Правила:\n"
            f"- Максимум {self.max_sub_queries} подзапроса(ов).\n"
            "- Каждый подзапрос должен быть самодостаточным: включай все сущности явно.\n"
            "- НЕ используй местоимения (это, они, там, его и т.п.).\n"
            "- Если это запрос на сравнение: выдели отдельные подзапросы по критериям "
            "(функционал, интеграции, стоимость, внедрение/поддержка).\n"
            "- Если это логическая связка (\"если ... то\", \"почему\", \"как связано\"): "
            "выдели отдельные подзапросы для причины, условия и последствия.\n"
            "- Для каждого подзапроса выбери релевантные категории из списка.\n"
            f"- Допустимые категории: {categories}\n"
            "Верни JSON строго по схеме.\n"
            f"Запрос клиента: {query}"
        )

        try:
            raw = self.llm.generate_structured(prompt, DecompositionResult)
        except Exception as e:
            logger.warning("Query decomposition failed", error=str(e))
            return None

        if raw is None:
            return None

        try:
            result = raw if isinstance(raw, DecompositionResult) else DecompositionResult.model_validate(raw)
        except Exception as e:
            logger.warning("Invalid decomposition payload", error=str(e))
            return None

        cleaned_sub_queries: List[SubQuery] = []
        for sub_query in result.sub_queries:
            text = (sub_query.query or "").strip()
            if not text:
                continue
            categories = [
                c.strip()
                for c in sub_query.categories
                if isinstance(c, str) and c.strip()
            ]
            cleaned_sub_queries.append(SubQuery(query=text, categories=categories))
            if len(cleaned_sub_queries) >= self.max_sub_queries:
                break

        return DecompositionResult(
            is_complex=result.is_complex,
            sub_queries=cleaned_sub_queries,
        )


class MultiQueryRetriever:
    """Runs multi-query retrieval and merges rankings with RRF."""

    def __init__(self, rrf_k: int = 60):
        self.rrf_k = max(1, rrf_k)

    def run(
        self,
        retriever: Any,
        base_query: str,
        base_categories: Optional[List[str]],
        sub_queries: Sequence[SubQuery],
        top_k_per_query: int,
    ) -> Tuple[List[SearchResult], List[SearchResult], List[List[SearchResult]]]:
        base_results = retriever.search(
            base_query,
            categories=base_categories,
            top_k=top_k_per_query,
        )
        sub_results = self.search_sub_queries(
            retriever=retriever,
            sub_queries=sub_queries,
            top_k_per_query=top_k_per_query,
        )
        merged = self.merge_rankings([base_results, *sub_results])
        return base_results, merged, sub_results

    def search_sub_queries(
        self,
        retriever: Any,
        sub_queries: Sequence[SubQuery],
        top_k_per_query: int,
    ) -> List[List[SearchResult]]:
        all_results: List[List[SearchResult]] = []
        for sub_query in sub_queries:
            results = retriever.search(
                sub_query.query,
                categories=sub_query.categories or None,
                top_k=top_k_per_query,
            )
            all_results.append(results)
        return all_results

    def merge_rankings(self, rankings: Sequence[Sequence[SearchResult]]) -> List[SearchResult]:
        rrf_scores: Dict[str, float] = defaultdict(float)
        best_result: Dict[str, SearchResult] = {}
        best_rank: Dict[str, int] = {}

        for ranking in rankings:
            seen_in_ranking: Set[str] = set()
            for rank, result in enumerate(ranking, start=1):
                key = self._result_key(result)
                if key in seen_in_ranking:
                    continue
                seen_in_ranking.add(key)
                rrf_scores[key] += 1.0 / (self.rrf_k + rank)
                if key not in best_rank or rank < best_rank[key]:
                    best_rank[key] = rank
                    best_result[key] = result

        ordered_keys = sorted(
            rrf_scores.keys(),
            key=lambda key: (-rrf_scores[key], best_rank.get(key, 999999), key),
        )
        return [best_result[key] for key in ordered_keys]

    @staticmethod
    def _result_key(result: SearchResult) -> str:
        return f"{result.section.category}/{result.section.topic}"


class LongContextReorder:
    """Zigzag reordering to reduce lost-in-the-middle effects."""

    @staticmethod
    def reorder(results: Sequence[SearchResult]) -> List[SearchResult]:
        left: List[SearchResult] = []
        right: List[SearchResult] = []
        for idx, result in enumerate(results):
            if idx % 2 == 0:
                left.append(result)
            else:
                right.insert(0, result)
        return left + right


class EnhancedRetrievalPipeline:
    """End-to-end query-driven retrieval for autonomous flow."""
    STATE_CONTEXT_SEPARATOR = "\n=== КОНТЕКСТ ЭТАПА ===\n"
    _DIRECT_FACTUAL_LEXICAL_RE = re.compile(
        r"(?:сколько|какие?|какой|расскажите|посоветуй|поч[её]м|цен[аы]|стоимост"
        r"|можно\s+ли|есть\s+ли|как\s+работает|как\s+это\s+работает|чем\s+отлич"
        r"|какие\s+банки|какой\s+тариф|какие\s+тарифы|рассрочк|офд|маркировк|1[cс]\b)",
        re.IGNORECASE,
    )
    _DIRECT_FACTUAL_INTENT_PREFIXES = (
        "question_",
        "price_",
        "pricing_",
        "comparison",
        "cost_",
        "roi_",
    )
    _DIRECT_FACTUAL_INTENTS_EXACT = frozenset({
        "payment_terms",
        "company_info_question",
        "experience_question",
    })

    def __init__(self, llm: LLMProtocol, category_router: Optional[CategoryRouter] = None):
        self.llm = llm
        self.category_router = category_router

        self.max_kb_chars = int(settings.get_nested("enhanced_retrieval.max_kb_chars", MAX_KB_CHARS))
        self.top_k_per_sub_query = int(settings.get_nested("enhanced_retrieval.top_k_per_sub_query", 3))
        self.max_sub_queries = int(settings.get_nested("enhanced_retrieval.max_sub_queries", 4))
        self.min_complexity_length = int(settings.get_nested("enhanced_retrieval.min_complexity_length", 30))
        self.rrf_k = int(settings.get_nested("enhanced_retrieval.rrf_k", 60))
        self.rewrite_min_words = int(settings.get_nested("enhanced_retrieval.rewrite_min_words", 4))
        self.factual_state_backfill_max_chars = int(
            settings.get_nested("enhanced_retrieval.factual_state_backfill_max_chars", 1200)
        )
        self.reranker_top_k = int(settings.get_nested("enhanced_retrieval.reranker_top_k", 5))
        self.reranker_skip_on_direct_factual = bool(
            settings.get_nested("enhanced_retrieval.reranker_skip_on_direct_factual", True)
        )
        self.reranker_preserve_exact_on_factual = bool(
            settings.get_nested("enhanced_retrieval.reranker_preserve_exact_on_factual", True)
        )

        self.query_rewriter = QueryRewriter(llm=llm, rewrite_min_words=self.rewrite_min_words)
        self.complexity_detector = ComplexityDetector(min_complexity_length=self.min_complexity_length)
        self.query_decomposer = QueryDecomposer(llm=llm, max_sub_queries=self.max_sub_queries)
        self.multi_query_retriever = MultiQueryRetriever(rrf_k=self.rrf_k)

    # Secondary intents that are purely meta/social and never need KB retrieval.
    # Any NEW secondary intent NOT listed here triggers retrieval automatically.
    # Default-safe: retrieval ON unless explicitly excluded.
    _SOCIAL_ONLY_SECONDARY = frozenset({"request_brevity"})
    _DIMENSION_TO_CATEGORIES: Dict[str, Tuple[str, ...]] = {
        "product_fit": ("products", "features", "tis"),
        "pricing": ("pricing", "promotions"),
        "integrations": ("integrations",),
        "features": ("features", "products"),
        "equipment": ("equipment",),
        "security": ("fiscal", "stability"),
        "support": ("support",),
        "comparison": ("competitors", "products", "features", "pricing"),
        "implementation": ("support", "features"),
        "delivery": ("delivery",),
        "contact": ("support",),
        "demo": ("support", "products"),
    }

    def retrieve(
        self,
        user_message: str,
        intent: str,
        state: str,
        flow_config: Any,
        kb: Any,
        recently_used_keys: Optional[Set[str]] = None,
        history: Optional[List[Dict[str, Any]]] = None,
        secondary_intents: Optional[List[str]] = None,
        semantic_frame: Optional[Dict[str, Any]] = None,
        collected_data: Optional[dict] = None,
    ) -> Tuple[str, List[Dict[str, str]], List[str]]:
        recently_used = set(recently_used_keys or set())
        history = history or []
        frame_dims = self._extract_frame_dimensions(semantic_frame)
        frame_forced_categories = self._frame_categories(frame_dims)
        frame_price_requested = self._frame_price_requested(semantic_frame, frame_dims)
        frame_blocks_pricing = bool(frame_dims) and not frame_price_requested
        selection_resolved_query = self.query_rewriter.resolve_fact_disambiguation_selection(
            user_message=user_message,
            history=history,
        )
        has_disambiguation_selection = bool(selection_resolved_query)

        # [0] Fast path for non-factual intents.
        if intent in SKIP_RETRIEVAL_INTENTS:
            # Don't skip retrieval if user message contains explicit question markers
            # E.g. "у меня 2 точки. Что посоветуете — Lite или Standard?" → situation_provided
            # but has a question → needs KB facts.
            _msg_lower = (user_message or "").lower()
            # Simple but effective: any "?" in message = question → don't skip retrieval.
            # Plus minimal keyword fallback for messages without "?".
            _has_question = '?' in _msg_lower or bool(re.search(
                r'(?:сколько|какие?|какой|расскажите|посоветуй|почём|цен[аы]|стоимост'
                r'|можно\s+ли|надо\s+ли|нужно\s+ли|есть\s+ли'
                r'|poster|постер|iiko|r-keeper|р-кипер|1[cс]\b'
                r'|битрикс|тариф|mini|lite|standard|тис\b'
                r'|лучше|хуже|отличи|разниц|сравн|перейти|переход'
                r'|хочу\s+(?:узнать|понять)|интересует|подскаж)',
                _msg_lower,
            ))
            if has_disambiguation_selection:
                pass  # selection answer must go through query-driven retrieval
            elif _has_question:
                pass  # Fall through to full retrieval — message has explicit question
            # If ANY secondary intent needs KB data → DON'T skip
            elif secondary_intents and not set(secondary_intents).issubset(self._SOCIAL_ONLY_SECONDARY):
                pass  # Fall through to full retrieval
            elif frame_dims:
                pass  # Semantic frame detected meaningful dimension(s)
            else:
                return load_facts_for_state(
                    state=state,
                    flow_config=flow_config,
                    kb=kb,
                    recently_used_keys=recently_used,
                    collected_data=collected_data,
                )

        retriever = get_retriever()
        is_direct_factual_turn = self._is_direct_factual_turn(intent=intent, user_message=user_message)

        # [1] Rewrite follow-up query when needed.
        rewritten_query = selection_resolved_query or self.query_rewriter.rewrite(
            user_message=user_message,
            history=history,
        )

        # [2] Category routing (optional).
        categories = None
        if self.category_router is not None and rewritten_query:
            categories = self.category_router.route(rewritten_query)
        if frame_forced_categories:
            if categories is None:
                categories = list(frame_forced_categories)
            else:
                categories = self._merge_categories(categories, frame_forced_categories)

        # [2a] Ensure "pricing" category is included when tariff/price terms appear.
        # CategoryRouter may route "расскажите про тариф Mini" → "features" only,
        # missing the pricing section. Force-include "pricing" when tariff names
        # or explicit price words are in the query.
        if categories is not None:
            # Check BOTH rewritten_query and original user_message for keywords
            _q_low = ((rewritten_query or "") + " " + (user_message or "")).lower()
            _explicit_price_terms = bool(re.search(
                r"(?:\bтариф\w*|\bцен[аы]\w*|\bстоимост\w*|\bсколько\s+стоит|\bпоч[её]м|\bрассроч\w*)",
                _q_low,
            ))
            _needs_pricing = bool(re.search(
                r'(?:тариф|mini|lite|standard|pro|тис|мини|лайт|стандарт|про\b'
                r'|цен[аы]|стоимост|сколько\s+стои|почём|прайс|расценк'
                r'|оборудовани|комплект|моноблок|pos|принтер|сканер|вес[аы]'
                r'|офд|ofd|фискал|обучени|тренинг)',
                _q_low,
            ))
            if frame_blocks_pricing and not _explicit_price_terms:
                _needs_pricing = False
            if _needs_pricing and "pricing" not in categories:
                categories = list(categories) + ["pricing"]
            if frame_blocks_pricing and "pricing" in categories and not _explicit_price_terms:
                categories = [c for c in categories if c != "pricing"]
            # Also include "equipment" for hardware questions
            _needs_equipment = bool(re.search(
                r'(?:оборудовани|моноблок|pos|принтер|сканер|вес[аы]|комплект|ящик'
                r'|терминал|tsd|тсд)',
                _q_low,
            ))
            if _needs_equipment and "equipment" not in categories:
                categories = list(categories) + ["equipment"]
            # Include "fiscal" for OFD questions
            _needs_fiscal = bool(re.search(
                r'(?:офд|ofd|фискал|фиск\b)',
                _q_low,
            ))
            if _needs_fiscal and "fiscal" not in categories:
                categories = list(categories) + ["fiscal"]
            # Include "support" for support/training questions
            _needs_support = bool(re.search(
                r'(?:поддержк|обучени|тренинг|техподдержк)',
                _q_low,
            ))
            if _needs_support and "support" not in categories:
                categories = list(categories) + ["support"]
            # Include "integrations" for marketplace/bank/1C/API questions
            _needs_integrations = bool(re.search(
                r'(?:маркетплейс|ozon|wildberries|озон|вайлдберриз'
                r'|kaspi\s*магазин|каспи\s*магазин|halyk\s*market|халык\s*маркет'
                r'|kaspi\s*qr|каспи\s*qr|nfc|бесконтактн'
                r'|интеграци|маркировк|ismet|исмет|data\s*matrix'
                r'|эсф|снт|электронн\w+\s+счёт|электронн\w+\s+счет'
                r'|смешанн\w+\s+оплат|комбинированн\w+\s+оплат'
                r'|api\b|webhook|rest\s+api)',
                _q_low,
            ))
            if _needs_integrations and "integrations" not in categories:
                categories = list(categories) + ["integrations"]
            # Include "employees" for staff/cashier questions
            _needs_employees = bool(re.search(
                r'(?:сотрудник|кассир|персонал|штат\w*|смен[аы]\b'
                r'|права\s+доступ|ограничи\w+\s+доступ|контрол\w+\s+кассир'
                r'|зарплат|кадров)',
                _q_low,
            ))
            if _needs_employees and "employees" not in categories:
                categories = list(categories) + ["employees"]
            # Include "inventory" for warehouse/revision questions
            _needs_inventory = bool(re.search(
                r'(?:ревизи|инвентаризац|склад\w*\b|остатк\w*\b'
                r'|серийн\w+\s+номер|imei|партии|сроки\s+годност)',
                _q_low,
            ))
            if _needs_inventory and "inventory" not in categories:
                categories = list(categories) + ["inventory"]
            # Include "mobile" for mobile/phone/offline questions
            _needs_mobile = bool(re.search(
                r'(?:мобильн|с\s+телефон|офлайн|оффлайн|без\s+интернет'
                r'|android|ios|планшет|push\s*уведомлен)',
                _q_low,
            ))
            if _needs_mobile and "mobile" not in categories:
                categories = list(categories) + ["mobile"]
            # Include "analytics" for analytics/reports questions
            _needs_analytics = bool(re.search(
                r'(?:аналитик|abc.анализ|маржинальн|себестоимост'
                r'|отчёт\w*\s+по\s+(?:прибыл|продаж|кассир|сотрудник))',
                _q_low,
            ))
            if _needs_analytics and "analytics" not in categories:
                categories = list(categories) + ["analytics"]
            # Include "delivery" for delivery/logistics/region questions
            _needs_delivery = bool(re.search(
                r'(?:доставк|доставля|доставит|привез|привёз|курьер'
                r'|самовывоз|логист|отправк|отправит)',
                _q_low,
            ))
            if _needs_delivery and "delivery" not in categories:
                categories = list(categories) + ["delivery"]

        # [3] Base query retrieval.
        base_results: List[SearchResult] = []
        if rewritten_query:
            base_results = retriever.search(
                rewritten_query,
                categories=categories,
                top_k=20,
            )

        # [3.5] Dual-query retrieval: merge rewritten query with original query.
        original_stripped = (user_message or "").strip()
        if (
            rewritten_query
            and original_stripped
            and rewritten_query != original_stripped
        ):
            original_results = retriever.search(
                original_stripped,
                categories=categories,
                top_k=10,
            )
            base_results = self.multi_query_retriever.merge_rankings([base_results, original_results])

        # [4] Decomposition + multi-query RRF merge.
        ranked_results = base_results
        if rewritten_query and self.complexity_detector.is_complex(rewritten_query):
            decomposition = self.query_decomposer.decompose(rewritten_query)
            if decomposition is not None and decomposition.sub_queries:
                sub_results = self.multi_query_retriever.search_sub_queries(
                    retriever=retriever,
                    sub_queries=decomposition.sub_queries[: self.max_sub_queries],
                    top_k_per_query=self.top_k_per_sub_query,
                )
                ranked_results = self.multi_query_retriever.merge_rankings([base_results, *sub_results])

        # [4.5] Cross-encoder reranking over hybrid candidates.
        pre_rerank_candidates = ranked_results[:20]
        reranker = get_reranker()
        if reranker.is_available() and len(pre_rerank_candidates) > 1:
            if self.reranker_skip_on_direct_factual and is_direct_factual_turn:
                ranked_results = pre_rerank_candidates[: self.reranker_top_k]
            else:
                reranked = reranker.rerank(
                    rewritten_query,
                    pre_rerank_candidates,
                    top_k=self.reranker_top_k,
                )
                if self.reranker_preserve_exact_on_factual and is_direct_factual_turn:
                    reranked_keys = {self._result_key(r) for r in reranked}
                    lexical_anchors = [
                        candidate
                        for candidate in pre_rerank_candidates[:10]
                        if self._is_lexical_anchor(candidate)
                    ]
                    if lexical_anchors and not any(
                        self._result_key(anchor) in reranked_keys
                        for anchor in lexical_anchors
                    ):
                        logger.info(
                            "Reranker dropped lexical anchors on factual query, fallback to pre-rerank",
                            intent=intent,
                            query=(user_message or "")[:120],
                        )
                        ranked_results = pre_rerank_candidates[: self.reranker_top_k]
                    else:
                        ranked_results = reranked
                else:
                    ranked_results = reranked

        # [5] Long-context reorder before text formatting.
        reordered_results = LongContextReorder.reorder(ranked_results)

        # [5.5] Fact rotation: deprioritize recently-used sections in query results.
        # Mirrors the fresh→seen ordering in autonomous_kb.load_facts_for_state().
        if recently_used:
            fresh_qr = [r for r in reordered_results
                        if f"{r.section.category}/{r.section.topic}" not in recently_used]
            seen_qr = [r for r in reordered_results
                       if f"{r.section.category}/{r.section.topic}" in recently_used]
            reordered_results = fresh_qr + seen_qr

        # [6] Sensitive filter + formatting + query context cap.
        query_facts_text, query_urls, query_fact_keys = self._build_query_context(reordered_results)

        # [7] Load state facts and truncate to remaining budget.
        state_recently_used = recently_used | set(query_fact_keys)
        state_text, state_urls, state_fact_keys = load_facts_for_state(
            state=state,
            flow_config=flow_config,
            kb=kb,
            recently_used_keys=state_recently_used,
            collected_data=collected_data,
        )
        remaining = self.max_kb_chars - len(query_facts_text)
        if query_facts_text:
            # Reserve separator budget only when both contexts are present.
            remaining -= len(self.STATE_CONTEXT_SEPARATOR)
        remaining = max(0, remaining)
        state_budget = remaining
        if is_direct_factual_turn and query_fact_keys:
            state_budget = min(state_budget, self.factual_state_backfill_max_chars)
        if len(state_text) > state_budget:
            state_text = state_text[:state_budget]

        # [8] Merge query-driven context with state context.
        facts_text = self._merge_context_text(query_facts_text, state_text)
        if len(facts_text) > self.max_kb_chars:
            facts_text = facts_text[:self.max_kb_chars]
        urls = self._merge_urls(query_urls, state_urls)
        fact_keys = self._merge_fact_keys(query_fact_keys, state_fact_keys)

        return facts_text, urls, fact_keys

    def _build_query_context(
        self,
        results: Sequence[SearchResult],
    ) -> Tuple[str, List[Dict[str, str]], List[str]]:
        facts_parts: List[str] = []
        urls: List[Dict[str, str]] = []
        used_keys: List[str] = []
        seen_fact_keys: Set[str] = set()
        seen_urls: Set[str] = set()
        total_chars = 0

        filtered_results = [r for r in results if not r.section.sensitive]

        for result in filtered_results:
            section = result.section
            key = f"{section.category}/{section.topic}"
            if key in seen_fact_keys:
                continue
            seen_fact_keys.add(key)

            clean_facts = _KB_META_STRIP_RE.sub("", section.facts or "")
            section_text = f"[{section.category}/{section.topic}]\n{clean_facts}\n"
            section_len = len(section_text)

            if total_chars + section_len > self.max_kb_chars:
                remaining = self.max_kb_chars - total_chars
                if remaining > 200:
                    # Keep total length within budget including ellipsis.
                    facts_parts.append(section_text[: max(0, remaining - 3)] + "...")
                    used_keys.append(key)
                    for url_info in section.urls or []:
                        url = url_info.get("url", "")
                        if url and url not in seen_urls:
                            urls.append(url_info)
                            seen_urls.add(url)
                    total_chars = self.max_kb_chars
                break

            facts_parts.append(section_text)
            used_keys.append(key)
            total_chars += section_len

            for url_info in section.urls or []:
                url = url_info.get("url", "")
                if url and url not in seen_urls:
                    urls.append(url_info)
                    seen_urls.add(url)

        facts_text = "".join(facts_parts)
        if len(facts_text) > self.max_kb_chars:
            facts_text = facts_text[:self.max_kb_chars]
        return facts_text, urls, used_keys

    @classmethod
    def _merge_context_text(cls, query_facts: str, state_facts: str) -> str:
        if query_facts and state_facts:
            return f"{query_facts}{cls.STATE_CONTEXT_SEPARATOR}{state_facts}"
        return query_facts or state_facts

    @staticmethod
    def _merge_urls(
        query_urls: List[Dict[str, str]],
        state_urls: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        merged: List[Dict[str, str]] = []
        seen: Set[str] = set()
        for url_info in [*query_urls, *state_urls]:
            url = (url_info or {}).get("url", "")
            if not url or url in seen:
                continue
            merged.append(url_info)
            seen.add(url)
        return merged

    @staticmethod
    def _merge_fact_keys(query_keys: List[str], state_keys: List[str]) -> List[str]:
        merged: List[str] = []
        seen: Set[str] = set()
        for key in [*query_keys, *state_keys]:
            if not key or key in seen:
                continue
            merged.append(key)
            seen.add(key)
        return merged

    @classmethod
    def _extract_frame_dimensions(cls, semantic_frame: Optional[Dict[str, Any]]) -> Set[str]:
        if not isinstance(semantic_frame, dict):
            return set()
        dims = semantic_frame.get("asked_dimensions", [])
        if not isinstance(dims, list):
            return set()
        return {str(d).strip().lower() for d in dims if d}

    @classmethod
    def _frame_categories(cls, frame_dims: Set[str]) -> List[str]:
        categories: List[str] = []
        for dim in frame_dims:
            for category in cls._DIMENSION_TO_CATEGORIES.get(dim, ()):
                if category not in categories:
                    categories.append(category)
        return categories

    @staticmethod
    def _frame_price_requested(
        semantic_frame: Optional[Dict[str, Any]],
        frame_dims: Set[str],
    ) -> bool:
        if "pricing" in frame_dims:
            return True
        if not isinstance(semantic_frame, dict):
            return False
        return bool(semantic_frame.get("price_requested"))

    @staticmethod
    def _merge_categories(base: Sequence[str], extra: Sequence[str]) -> List[str]:
        merged: List[str] = []
        for category in [*list(base), *list(extra)]:
            if category and category not in merged:
                merged.append(category)
        return merged

    @classmethod
    def _looks_like_direct_factual_question(cls, user_message: str) -> bool:
        msg = (user_message or "").strip()
        if not msg:
            return False
        if "?" in msg:
            return True
        return bool(cls._DIRECT_FACTUAL_LEXICAL_RE.search(msg))

    @classmethod
    def _is_direct_factual_turn(cls, intent: str, user_message: str) -> bool:
        normalized_intent = str(intent or "").lower().strip()
        if not normalized_intent:
            return False
        is_factual_intent = (
            normalized_intent.startswith(cls._DIRECT_FACTUAL_INTENT_PREFIXES)
            or normalized_intent in cls._DIRECT_FACTUAL_INTENTS_EXACT
        )
        if not is_factual_intent:
            return False
        return cls._looks_like_direct_factual_question(user_message)

    @staticmethod
    def _is_lexical_anchor(result: SearchResult) -> bool:
        if getattr(result, "matched_keywords", None):
            return True
        if getattr(result, "matched_lemmas", None):
            return True
        return False


__all__ = [
    "SubQuery",
    "DecompositionResult",
    "QueryRewriter",
    "ComplexityDetector",
    "QueryDecomposer",
    "MultiQueryRetriever",
    "LongContextReorder",
    "EnhancedRetrievalPipeline",
]
