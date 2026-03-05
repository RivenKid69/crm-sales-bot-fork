#!/usr/bin/env python3
"""
Full-chain root-cause audit for autonomous retrieval flow.

Runs two layers:
1) Retrieval-only diagnostics (expected fact-key pattern hit/miss).
2) E2E dialog diagnostics (expected factual signals in final bot responses).

Then classifies misses into root-cause buckets and writes:
- results/root_cause_chain_audit_<timestamp>.json
- results/root_cause_chain_report.md
"""

from __future__ import annotations

import copy
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import benchmark_retrieval_stages as retrieval_suite
from scripts import kb_verify as kb_v1
from scripts import kb_verify_wave2 as kb_v2
from src.bot import SalesBot, setup_autonomous_pipeline
from src.config_loader import ConfigLoader
from src.knowledge.autonomous_kb import load_facts_for_state
from src.knowledge.category_router import CategoryRouter
from src.knowledge.enhanced_retrieval import (
    DecompositionResult,
    EnhancedRetrievalPipeline,
    LongContextReorder,
    SubQuery,
)
from src.knowledge.loader import load_knowledge_base
from src.knowledge.reranker import get_reranker
from src.knowledge.retriever import (
    SKIP_RETRIEVAL_INTENTS,
    CascadeRetriever,
    SearchResult,
    get_retriever,
    reset_retriever,
)
from src.llm import OllamaLLM
from src.settings import settings


def result_key(result: SearchResult) -> str:
    return f"{result.section.category}/{result.section.topic}"


def first_pattern_rank(keys: Sequence[str], patterns: Sequence[str]) -> Optional[int]:
    if not patterns:
        return None
    lowered_patterns = [p.lower() for p in patterns]
    for idx, key in enumerate(keys, 1):
        key_l = key.lower()
        if any(p in key_l for p in lowered_patterns):
            return idx
    return None


def has_any_keyword(text: str, keywords: Sequence[str]) -> bool:
    text_l = (text or "").lower()
    return any(k.lower() in text_l for k in keywords)


def flatten_kb_text(sections: Sequence[Any]) -> str:
    parts: List[str] = []
    for section in sections:
        parts.append((section.facts or "").lower())
        parts.extend((kw or "").lower() for kw in (section.keywords or []))
        parts.append(f"{section.category}/{section.topic}".lower())
    return "\n".join(parts)


def infer_secondary_intents(context: Dict[str, Any]) -> List[str]:
    raw = context.get("classification") or {}
    if not isinstance(raw, dict):
        return []
    sec = raw.get("secondary_intents") or []
    if isinstance(sec, list):
        return [str(x) for x in sec if isinstance(x, str)]
    return []


def apply_force_include_categories(
    categories: Optional[List[str]],
    rewritten_query: str,
    user_message: str,
) -> Optional[List[str]]:
    """
    Mirror the force-include block from EnhancedRetrievalPipeline.retrieve().
    """
    if categories is None:
        return None

    out = list(categories)
    q_low = ((rewritten_query or "") + " " + (user_message or "")).lower()

    def ensure(cat: str, pattern: str) -> None:
        nonlocal out
        if re.search(pattern, q_low) and cat not in out:
            out = out + [cat]

    ensure(
        "pricing",
        r"(?:тариф|mini|lite|standard|pro|тис|мини|лайт|стандарт|про\b"
        r"|цен[аы]|стоимост|сколько\s+стои|почём|прайс|расценк"
        r"|оборудовани|комплект|моноблок|pos|принтер|сканер|вес[аы]"
        r"|офд|ofd|фискал|обучени|тренинг)",
    )
    ensure(
        "equipment",
        r"(?:оборудовани|моноблок|pos|принтер|сканер|вес[аы]|комплект|ящик"
        r"|терминал|tsd|тсд)",
    )
    ensure("fiscal", r"(?:офд|ofd|фискал|фиск\b)")
    ensure("support", r"(?:поддержк|обучени|тренинг|техподдержк)")
    ensure(
        "integrations",
        r"(?:маркетплейс|ozon|wildberries|озон|вайлдберриз"
        r"|kaspi\s*магазин|каспи\s*магазин|halyk\s*market|халык\s*маркет"
        r"|kaspi\s*qr|каспи\s*qr|nfc|бесконтактн"
        r"|интеграци|маркировк|ismet|исмет|data\s*matrix"
        r"|эсф|снт|электронн\w+\s+счёт|электронн\w+\s+счет"
        r"|смешанн\w+\s+оплат|комбинированн\w+\s+оплат"
        r"|api\b|webhook|rest\s+api)",
    )
    ensure(
        "employees",
        r"(?:сотрудник|кассир|персонал|штат\w*|смен[аы]\b"
        r"|права\s+доступ|ограничи\w+\s+доступ|контрол\w+\s+кассир"
        r"|зарплат|кадров)",
    )
    ensure(
        "inventory",
        r"(?:ревизи|инвентаризац|склад\w*\b|остатк\w*\b"
        r"|серийн\w+\s+номер|imei|партии|сроки\s+годност)",
    )
    ensure(
        "mobile",
        r"(?:мобильн|с\s+телефон|офлайн|оффлайн|без\s+интернет"
        r"|android|ios|планшет|push\s*уведомлен)",
    )
    ensure(
        "analytics",
        r"(?:аналитик|abc.анализ|маржинальн|себестоимост"
        r"|отчёт\w*\s+по\s+(?:прибыл|продаж|кассир|сотрудник))",
    )
    return out


def should_skip_retrieval(
    intent: str,
    user_message: str,
    secondary_intents: Sequence[str],
) -> bool:
    if intent not in SKIP_RETRIEVAL_INTENTS:
        return False

    msg_lower = (user_message or "").lower()
    has_question = "?" in msg_lower or bool(
        re.search(
            r"(?:сколько|какие?|какой|расскажите|посоветуй|почём|цен[аы]|стоимост"
            r"|можно\s+ли|надо\s+ли|нужно\s+ли|есть\s+ли"
            r"|poster|постер|iiko|r-keeper|р-кипер|1[cс]\b"
            r"|битрикс|тариф|mini|lite|standard|тис\b"
            r"|лучше|хуже|отличи|разниц|сравн|перейти|переход"
            r"|хочу\s+(?:узнать|понять)|интересует|подскаж)",
            msg_lower,
        )
    )
    if has_question:
        return False

    social_only = frozenset({"request_brevity"})
    if secondary_intents and not set(secondary_intents).issubset(social_only):
        return False
    return True


@dataclass
class RetrievalDiagnostics:
    query: str
    intent: str
    state: str
    rewritten_query: str
    rewrite_changed: bool
    categories: Optional[List[str]]
    skip_fast_path: bool
    decomposition_used: bool
    sub_queries: List[str]
    reranker_used: bool
    base_keys: List[str]
    pre_rerank_keys: List[str]
    post_rerank_keys: List[str]
    query_fact_keys: List[str]
    final_fact_keys: List[str]
    query_facts_len: int
    final_facts_len: int
    elapsed_ms: float


def diagnose_retrieval(
    *,
    pipeline: EnhancedRetrievalPipeline,
    retriever: CascadeRetriever,
    user_message: str,
    intent: str,
    state: str,
    flow_config: Any,
    kb: Any,
    history: Optional[List[Dict[str, Any]]] = None,
    secondary_intents: Optional[List[str]] = None,
    collected_data: Optional[dict] = None,
    recently_used_keys: Optional[Set[str]] = None,
) -> RetrievalDiagnostics:
    """
    Reproduce EnhancedRetrievalPipeline.retrieve() with extra intermediate traces.
    """
    start = time.perf_counter()
    history = history or []
    secondary_intents = secondary_intents or []
    recently_used = set(recently_used_keys or set())

    skip_fast_path = should_skip_retrieval(intent, user_message, secondary_intents)
    rewritten_query = pipeline.query_rewriter.rewrite(user_message=user_message, history=history)
    original_query = (user_message or "").strip()

    if skip_fast_path:
        facts_text, _urls, fact_keys = load_facts_for_state(
            state=state,
            flow_config=flow_config,
            kb=kb,
            recently_used_keys=recently_used,
            collected_data=collected_data,
        )
        elapsed = (time.perf_counter() - start) * 1000
        return RetrievalDiagnostics(
            query=user_message,
            intent=intent,
            state=state,
            rewritten_query=rewritten_query,
            rewrite_changed=bool(rewritten_query and rewritten_query != original_query),
            categories=None,
            skip_fast_path=True,
            decomposition_used=False,
            sub_queries=[],
            reranker_used=False,
            base_keys=[],
            pre_rerank_keys=[],
            post_rerank_keys=[],
            query_fact_keys=[],
            final_fact_keys=fact_keys,
            query_facts_len=0,
            final_facts_len=len(facts_text),
            elapsed_ms=elapsed,
        )

    categories = None
    if pipeline.category_router is not None and rewritten_query:
        categories = pipeline.category_router.route(rewritten_query)
    categories = apply_force_include_categories(categories, rewritten_query, user_message)

    base_results: List[SearchResult] = []
    if rewritten_query:
        base_results = retriever.search(rewritten_query, categories=categories, top_k=20)

    if rewritten_query and original_query and rewritten_query != original_query:
        orig_results = retriever.search(original_query, categories=categories, top_k=10)
        base_results = pipeline.multi_query_retriever.merge_rankings([base_results, orig_results])

    ranked_results = list(base_results)
    decomposition_used = False
    sub_queries: List[str] = []
    if rewritten_query and pipeline.complexity_detector.is_complex(rewritten_query):
        decomposition = pipeline.query_decomposer.decompose(rewritten_query)
        if decomposition is not None and decomposition.sub_queries:
            decomposition_used = True
            sub_queries = [sq.query for sq in decomposition.sub_queries[: pipeline.max_sub_queries]]
            sub_results = pipeline.multi_query_retriever.search_sub_queries(
                retriever=retriever,
                sub_queries=decomposition.sub_queries[: pipeline.max_sub_queries],
                top_k_per_query=pipeline.top_k_per_sub_query,
            )
            ranked_results = pipeline.multi_query_retriever.merge_rankings([base_results, *sub_results])

    is_direct_factual_turn = pipeline._is_direct_factual_turn(
        intent=intent,
        user_message=user_message,
    )

    pre_rerank = list(ranked_results[:20])
    reranker_used = False
    reranker = get_reranker()
    if reranker.is_available() and len(pre_rerank) > 1:
        if pipeline.reranker_skip_on_direct_factual and is_direct_factual_turn:
            ranked_results = pre_rerank[: pipeline.reranker_top_k]
        else:
            reranker_used = True
            reranked = reranker.rerank(
                rewritten_query,
                pre_rerank,
                top_k=pipeline.reranker_top_k,
            )
            if pipeline.reranker_preserve_exact_on_factual and is_direct_factual_turn:
                reranked_keys = {result_key(r) for r in reranked}
                lexical_anchors = [
                    candidate
                    for candidate in pre_rerank[:10]
                    if pipeline._is_lexical_anchor(candidate)
                ]
                if lexical_anchors and not any(
                    result_key(anchor) in reranked_keys
                    for anchor in lexical_anchors
                ):
                    ranked_results = pre_rerank[: pipeline.reranker_top_k]
                else:
                    ranked_results = reranked
            else:
                ranked_results = reranked

    post_rerank = list(ranked_results)
    reordered = LongContextReorder.reorder(ranked_results)

    if recently_used:
        fresh_qr = [r for r in reordered if result_key(r) not in recently_used]
        seen_qr = [r for r in reordered if result_key(r) in recently_used]
        reordered = fresh_qr + seen_qr

    query_facts_text, query_urls, query_fact_keys = pipeline._build_query_context(reordered)

    state_recently_used = recently_used | set(query_fact_keys)
    state_text, state_urls, state_fact_keys = load_facts_for_state(
        state=state,
        flow_config=flow_config,
        kb=kb,
        recently_used_keys=state_recently_used,
        collected_data=collected_data,
    )
    remaining = pipeline.max_kb_chars - len(query_facts_text)
    if query_facts_text:
        remaining -= len(pipeline.STATE_CONTEXT_SEPARATOR)
    remaining = max(0, remaining)
    state_budget = remaining
    if is_direct_factual_turn and query_fact_keys:
        state_budget = min(state_budget, pipeline.factual_state_backfill_max_chars)
    if len(state_text) > state_budget:
        state_text = state_text[:state_budget]

    facts_text = pipeline._merge_context_text(query_facts_text, state_text)
    if len(facts_text) > pipeline.max_kb_chars:
        facts_text = facts_text[: pipeline.max_kb_chars]

    _urls = pipeline._merge_urls(query_urls, state_urls)
    final_fact_keys = pipeline._merge_fact_keys(query_fact_keys, state_fact_keys)

    elapsed = (time.perf_counter() - start) * 1000
    return RetrievalDiagnostics(
        query=user_message,
        intent=intent,
        state=state,
        rewritten_query=rewritten_query,
        rewrite_changed=bool(rewritten_query and rewritten_query != original_query),
        categories=categories,
        skip_fast_path=False,
        decomposition_used=decomposition_used,
        sub_queries=sub_queries,
        reranker_used=reranker_used,
        base_keys=[result_key(r) for r in base_results],
        pre_rerank_keys=[result_key(r) for r in pre_rerank],
        post_rerank_keys=[result_key(r) for r in post_rerank],
        query_fact_keys=query_fact_keys,
        final_fact_keys=final_fact_keys,
        query_facts_len=len(query_facts_text),
        final_facts_len=len(facts_text),
        elapsed_ms=elapsed,
    )


def classify_retrieval_failure(
    *,
    diag: RetrievalDiagnostics,
    expected_patterns: Sequence[str],
    retriever: CascadeRetriever,
    kb_keys: Sequence[str],
) -> Tuple[str, Dict[str, Any]]:
    details: Dict[str, Any] = {}

    if not expected_patterns:
        return "negative_case", details

    lower_patterns = [p.lower() for p in expected_patterns]
    pattern_exists_in_kb = any(any(p in key.lower() for p in lower_patterns) for key in kb_keys)
    details["pattern_exists_in_kb"] = pattern_exists_in_kb

    top5_rank = first_pattern_rank(diag.query_fact_keys[:5], expected_patterns)
    pre_rerank_rank = first_pattern_rank(diag.pre_rerank_keys[:20], expected_patterns)
    base_rank = first_pattern_rank(diag.base_keys[:20], expected_patterns)
    broad_keys = [result_key(r) for r in retriever.search(diag.query, categories=None, top_k=50)]
    broad_rank = first_pattern_rank(broad_keys, expected_patterns)

    details.update({
        "top5_rank": top5_rank,
        "pre_rerank_rank": pre_rerank_rank,
        "base_rank": base_rank,
        "broad_rank": broad_rank,
    })

    if top5_rank is not None:
        return "ok", details

    if not pattern_exists_in_kb:
        return "benchmark_expectation_mismatch", details

    if pre_rerank_rank is not None and (top5_rank is None):
        return "reranker_or_cutoff_regression", details

    if base_rank is not None and pre_rerank_rank is None:
        return "decomposition_merge_noise", details

    if broad_rank is not None and base_rank is None:
        if diag.rewrite_changed:
            return "rewrite_or_scope_loss", details
        return "orchestration_ranking_loss", details

    if broad_rank is not None and broad_rank > 5:
        return "ranking_depth_issue", details

    return "retrieval_recall_gap", details


def run_retrieval_audit(
    *,
    llm: OllamaLLM,
    flow_config: Any,
    kb: Any,
) -> Dict[str, Any]:
    if settings.get_nested("category_router.enabled", False):
        router = CategoryRouter(llm, top_k=int(settings.get_nested("category_router.top_k", 3)))
    else:
        router = None

    pipeline = EnhancedRetrievalPipeline(llm=llm, category_router=router)
    retriever = get_retriever()

    kb_keys = [f"{s.category}/{s.topic}" for s in kb.sections]
    cases = retrieval_suite.TESTS

    per_case: List[Dict[str, Any]] = []
    failure_buckets = Counter()
    group_stats: Dict[str, Counter] = defaultdict(Counter)
    hit_top5 = 0
    hit_pre20 = 0
    rewrite_changed = 0
    decomposition_used = 0
    reranker_used = 0

    for case in cases:
        diag = diagnose_retrieval(
            pipeline=pipeline,
            retriever=retriever,
            user_message=case.query,
            intent=case.intent,
            state=case.state,
            flow_config=flow_config,
            kb=kb,
            history=[],
            secondary_intents=[],
            collected_data={},
            recently_used_keys=set(),
        )

        if diag.rewrite_changed:
            rewrite_changed += 1
        if diag.decomposition_used:
            decomposition_used += 1
        if diag.reranker_used:
            reranker_used += 1

        rank_top5 = first_pattern_rank(diag.query_fact_keys[:5], case.expected)
        rank_pre20 = first_pattern_rank(diag.pre_rerank_keys[:20], case.expected)
        is_hit_top5 = case.expected == [] or rank_top5 is not None
        is_hit_pre20 = case.expected == [] or rank_pre20 is not None
        if is_hit_top5:
            hit_top5 += 1
        if is_hit_pre20:
            hit_pre20 += 1

        root_cause, details = classify_retrieval_failure(
            diag=diag,
            expected_patterns=case.expected,
            retriever=retriever,
            kb_keys=kb_keys,
        )
        if root_cause != "ok" and root_cause != "negative_case":
            failure_buckets[root_cause] += 1
            group_stats[case.group][root_cause] += 1

        per_case.append({
            "query": case.query,
            "desc": case.desc,
            "group": case.group,
            "expected_patterns": case.expected,
            "hit_top5": is_hit_top5,
            "hit_pre20": is_hit_pre20,
            "rank_top5": rank_top5,
            "rank_pre20": rank_pre20,
            "root_cause": root_cause,
            "root_details": details,
            "diagnostics": asdict(diag),
        })

    total = len(cases)
    return {
        "summary": {
            "cases_total": total,
            "hit_top5": hit_top5,
            "hit_top5_rate": round(hit_top5 / max(total, 1), 4),
            "hit_pre20": hit_pre20,
            "hit_pre20_rate": round(hit_pre20 / max(total, 1), 4),
            "rewrite_changed_rate": round(rewrite_changed / max(total, 1), 4),
            "decomposition_used_rate": round(decomposition_used / max(total, 1), 4),
            "reranker_used_rate": round(reranker_used / max(total, 1), 4),
            "failure_buckets": dict(failure_buckets),
        },
        "group_failure_buckets": {k: dict(v) for k, v in group_stats.items()},
        "cases": per_case,
    }


def _merge_scenarios() -> List[Tuple[str, List[str], Dict[str, Any], Any]]:
    out: List[Tuple[str, List[str], Dict[str, Any], Any]] = []
    for name, msgs in kb_v1.SCENARIOS.items():
        out.append((name, msgs, kb_v1.EXPECTED_FACTS.get(name, {}), kb_v1.check_facts))
    for name, msgs in kb_v2.SCENARIOS.items():
        out.append((name, msgs, kb_v2.EXPECTED_FACTS.get(name, {}), kb_v2.check_facts))
    return out


def classify_e2e_failure(
    *,
    check_result: Dict[str, Any],
    expected: Dict[str, Any],
    bot_responses: Sequence[str],
    retrieved_facts_text: str,
    kb_text: str,
    facts_len: int,
) -> Tuple[str, Dict[str, Any]]:
    details: Dict[str, Any] = {
        "facts_len": facts_len,
        "issues": check_result.get("issues", []),
    }
    if check_result.get("pass"):
        return "ok", details

    expected_any = expected.get("must_contain_any", []) or []
    expected_all = expected.get("must_contain_all", []) or []
    forbidden = expected.get("must_not_contain", []) or []

    all_bot_text = " ".join(bot_responses).lower()
    retrieved_l = (retrieved_facts_text or "").lower()

    in_kb_any = any(k.lower() in kb_text for k in expected_any) if expected_any else True
    in_ret_any = has_any_keyword(retrieved_l, expected_any) if expected_any else True
    in_resp_any = has_any_keyword(all_bot_text, expected_any) if expected_any else True
    details.update({
        "expected_any_in_kb": in_kb_any,
        "expected_any_in_retrieved": in_ret_any,
        "expected_any_in_response": in_resp_any,
    })

    if expected_all:
        missing_all = [kw for kw in expected_all if kw.lower() not in all_bot_text]
        details["missing_all"] = missing_all

    if forbidden:
        forbidden_found = [kw for kw in forbidden if kw.lower() in all_bot_text]
        if forbidden_found:
            details["forbidden_found"] = forbidden_found
            return "forbidden_claims_in_response", details

    if expected_any and not in_kb_any:
        return "expected_signal_missing_in_kb", details
    if facts_len <= 0:
        return "empty_retrieval_context", details
    if expected_any and not in_ret_any:
        return "retrieval_miss_for_expected_signal", details
    if expected_any and in_ret_any and not in_resp_any:
        if facts_len >= 9500:
            return "generation_grounding_loss_with_budget_pressure", details
        return "generation_grounding_loss", details

    return "response_validation_mismatch", details


def run_e2e_audit(
    *,
    llm: OllamaLLM,
    flow_name: str,
    kb_text: str,
) -> Dict[str, Any]:
    setup_autonomous_pipeline()
    bot = SalesBot(llm, flow_name=flow_name, enable_tracing=True)
    scenarios = _merge_scenarios()

    per_scenario: List[Dict[str, Any]] = []
    failure_buckets = Counter()
    pass_count = 0
    total_turns = 0

    for name, messages, expected, check_fn in scenarios:
        bot.reset()
        trace: List[Dict[str, Any]] = []
        last_retrieve_trace: Dict[str, Any] = {}
        last_gen_meta: Dict[str, Any] = {}

        for idx, msg in enumerate(messages, 1):
            t0 = time.perf_counter()
            result = bot.process(msg)
            elapsed_ms = (time.perf_counter() - t0) * 1000

            gen_meta = bot.generator.get_last_generation_meta() or {}
            last_gen_meta = copy.deepcopy(gen_meta)
            pipeline = getattr(bot.generator, "_enhanced_pipeline", None)
            retrieve_trace = {}
            if pipeline is not None:
                retrieve_trace = copy.deepcopy(getattr(pipeline, "_debug_last_retrieve", {}))
                if retrieve_trace:
                    last_retrieve_trace = retrieve_trace

            trace.append({
                "turn": idx,
                "user": msg,
                "bot": result.get("response", ""),
                "state": result.get("state", ""),
                "intent": result.get("intent", ""),
                "action": result.get("action", ""),
                "elapsed_ms": round(elapsed_ms, 2),
                "fact_keys": gen_meta.get("fact_keys", []),
                "selected_template": gen_meta.get("selected_template_key"),
                "retrieve_trace_summary": {
                    "user_message": retrieve_trace.get("user_message"),
                    "intent": retrieve_trace.get("intent"),
                    "state": retrieve_trace.get("state"),
                    "fact_keys_count": len(retrieve_trace.get("fact_keys", []) or []),
                    "facts_len": retrieve_trace.get("facts_len", 0),
                    "elapsed_ms": retrieve_trace.get("elapsed_ms", 0),
                },
            })

            if result.get("is_final"):
                break

        total_turns += len(trace)
        bot_responses = [turn["bot"] for turn in trace]
        check_result = check_fn(name, bot_responses)
        retrieved_text = last_retrieve_trace.get("facts_text", "") if last_retrieve_trace else ""
        facts_len = int(last_retrieve_trace.get("facts_len", 0) or 0)
        root_cause, details = classify_e2e_failure(
            check_result=check_result,
            expected=expected,
            bot_responses=bot_responses,
            retrieved_facts_text=retrieved_text,
            kb_text=kb_text,
            facts_len=facts_len,
        )
        if check_result.get("pass"):
            pass_count += 1
        else:
            failure_buckets[root_cause] += 1

        per_scenario.append({
            "scenario": name,
            "expected": expected,
            "check": check_result,
            "root_cause": root_cause,
            "root_details": details,
            "last_generation_meta": last_gen_meta,
            "last_retrieve_trace": {
                **{k: v for k, v in last_retrieve_trace.items() if k != "facts_text"},
                "facts_preview": (retrieved_text[:500] + "...") if len(retrieved_text) > 500 else retrieved_text,
            },
            "trace": trace,
        })

    total = len(scenarios)
    return {
        "summary": {
            "scenarios_total": total,
            "scenarios_pass": pass_count,
            "scenarios_fail": total - pass_count,
            "pass_rate": round(pass_count / max(total, 1), 4),
            "avg_turns_per_scenario": round(total_turns / max(total, 1), 2),
            "failure_buckets": dict(failure_buckets),
        },
        "scenarios": per_scenario,
    }


def build_chain_summary(
    retrieval_audit: Dict[str, Any],
    e2e_audit: Dict[str, Any],
) -> Dict[str, Any]:
    retrieval_failures = Counter(retrieval_audit["summary"]["failure_buckets"])
    e2e_failures = Counter(e2e_audit["summary"]["failure_buckets"])

    stage_chain = {
        "retrieval_stage_issues": dict(retrieval_failures),
        "generation_stage_issues": dict(e2e_failures),
    }

    combined = retrieval_failures + e2e_failures
    top_roots = combined.most_common()

    return {
        "top_root_causes": [{"root_cause": k, "count": v} for k, v in top_roots],
        "stage_chain": stage_chain,
    }


def write_markdown_report(
    *,
    path: Path,
    chain_summary: Dict[str, Any],
    retrieval_audit: Dict[str, Any],
    e2e_audit: Dict[str, Any],
) -> None:
    lines: List[str] = []
    r = retrieval_audit["summary"]
    e = e2e_audit["summary"]

    lines.append("# Root Cause Chain Audit")
    lines.append("")
    lines.append("## Headline")
    lines.append(f"- Retrieval top-5 hit rate: {r['hit_top5']} / {r['cases_total']} ({r['hit_top5_rate']*100:.1f}%)")
    lines.append(f"- Retrieval pre-rerank@20 hit rate: {r['hit_pre20']} / {r['cases_total']} ({r['hit_pre20_rate']*100:.1f}%)")
    lines.append(f"- E2E factual pass rate: {e['scenarios_pass']} / {e['scenarios_total']} ({e['pass_rate']*100:.1f}%)")
    lines.append("")

    lines.append("## Top Root Causes")
    top_roots = chain_summary.get("top_root_causes", [])[:12]
    if not top_roots:
        lines.append("- none")
    else:
        for item in top_roots:
            lines.append(f"- {item['root_cause']}: {item['count']}")
    lines.append("")

    lines.append("## Retrieval Failure Buckets")
    for k, v in sorted(r.get("failure_buckets", {}).items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"- {k}: {v}")
    if not r.get("failure_buckets"):
        lines.append("- none")
    lines.append("")

    lines.append("## E2E Failure Buckets")
    for k, v in sorted(e.get("failure_buckets", {}).items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"- {k}: {v}")
    if not e.get("failure_buckets"):
        lines.append("- none")
    lines.append("")

    lines.append("## Sample Retrieval Misses")
    misses = [c for c in retrieval_audit["cases"] if c["root_cause"] not in {"ok", "negative_case"}]
    for case in misses[:10]:
        lines.append(f"- [{case['group']}] {case['query']}")
        lines.append(f"  root={case['root_cause']} expected={case['expected_patterns'][:3]}")
        lines.append(f"  top5={case['diagnostics']['query_fact_keys'][:5]}")
    if not misses:
        lines.append("- none")
    lines.append("")

    lines.append("## Sample E2E Fails")
    fails = [s for s in e2e_audit["scenarios"] if not s["check"].get("pass")]
    for item in fails[:12]:
        lines.append(f"- {item['scenario']}: {item['root_cause']}")
        lines.append(f"  issues={item['check'].get('issues', [])}")
        lines.append(f"  fact_keys={item.get('last_generation_meta', {}).get('fact_keys', [])[:5]}")
    if not fails:
        lines.append("- none")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def patch_pipeline_retrieve_for_tracing() -> None:
    original = EnhancedRetrievalPipeline.retrieve

    if getattr(EnhancedRetrievalPipeline, "_root_audit_patch_applied", False):
        return

    def traced(self: EnhancedRetrievalPipeline, *args: Any, **kwargs: Any):
        t0 = time.perf_counter()
        facts_text, urls, fact_keys = original(self, *args, **kwargs)

        user_message = ""
        intent = ""
        state = ""
        if args:
            user_message = str(args[0]) if len(args) > 0 else ""
            intent = str(args[1]) if len(args) > 1 else ""
            state = str(args[2]) if len(args) > 2 else ""
        user_message = kwargs.get("user_message", user_message)
        intent = kwargs.get("intent", intent)
        state = kwargs.get("state", state)

        self._debug_last_retrieve = {
            "user_message": user_message,
            "intent": intent,
            "state": state,
            "fact_keys": list(fact_keys or []),
            "facts_len": len(facts_text or ""),
            "urls_count": len(urls or []),
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
            "facts_text": facts_text or "",
        }
        return facts_text, urls, fact_keys

    EnhancedRetrievalPipeline.retrieve = traced  # type: ignore[assignment]
    EnhancedRetrievalPipeline._root_audit_patch_applied = True  # type: ignore[attr-defined]


def main() -> None:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_json = Path("results") / f"root_cause_chain_audit_{ts}.json"
    out_md = Path("results") / "root_cause_chain_report.md"
    out_json.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("ROOT-CAUSE CHAIN AUDIT")
    print("=" * 80)

    print("[1/6] Reset retriever singleton...")
    reset_retriever()

    print("[2/6] Loading KB + flow config...")
    kb = load_knowledge_base()
    loader = ConfigLoader()
    _cfg, flow_config = loader.load_bundle(config_name="default", flow_name="autonomous")
    kb_text = flatten_kb_text(kb.sections)
    print(f"       KB sections: {len(kb.sections)}")

    print("[3/6] Creating shared LLM client...")
    llm = OllamaLLM()
    if not llm.health_check():
        raise RuntimeError("Ollama is not available or model is not loaded.")

    print("[4/6] Patching retrieval tracing...")
    patch_pipeline_retrieve_for_tracing()

    print("[5/6] Running retrieval diagnostics suite...")
    retrieval_started = time.perf_counter()
    retrieval_audit = run_retrieval_audit(llm=llm, flow_config=flow_config, kb=kb)
    print(
        "       Retrieval done in %.1fs | top5=%.1f%% pre20=%.1f%%"
        % (
            time.perf_counter() - retrieval_started,
            retrieval_audit["summary"]["hit_top5_rate"] * 100,
            retrieval_audit["summary"]["hit_pre20_rate"] * 100,
        )
    )

    print("[6/6] Running full E2E factual diagnostics...")
    e2e_started = time.perf_counter()
    e2e_audit = run_e2e_audit(llm=llm, flow_name="autonomous", kb_text=kb_text)
    print(
        "       E2E done in %.1fs | pass=%.1f%%"
        % (
            time.perf_counter() - e2e_started,
            e2e_audit["summary"]["pass_rate"] * 100,
        )
    )

    chain_summary = build_chain_summary(retrieval_audit=retrieval_audit, e2e_audit=e2e_audit)

    payload = {
        "timestamp": ts,
        "settings_snapshot": {
            "retriever": settings.get_nested("retriever", {}),
            "category_router_enabled": settings.get_nested("category_router.enabled", False),
            "enhanced_retrieval": settings.get_nested("enhanced_retrieval", {}),
        },
        "retrieval_audit": retrieval_audit,
        "e2e_audit": e2e_audit,
        "chain_summary": chain_summary,
    }

    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown_report(
        path=out_md,
        chain_summary=chain_summary,
        retrieval_audit=retrieval_audit,
        e2e_audit=e2e_audit,
    )

    print("-" * 80)
    print(f"Saved JSON: {out_json}")
    print(f"Saved MD:   {out_md}")
    print("-" * 80)


if __name__ == "__main__":
    main()
