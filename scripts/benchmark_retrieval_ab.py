#!/usr/bin/env python3
"""
Point A/B retrieval benchmark:
- A (before): legacy short-circuit cascade
  semantic(top_k) -> exact(top_k) -> lemma(top_k)
- B (after): current hybrid search with RRF merge
  semantic(top_k*3) + exact + lemma -> RRF -> top_k

Outputs top-5 fact keys and snippets for each query to:
  results/benchmark_retrieval_ab.json
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from typing import List, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.knowledge.retriever import SearchResult, get_retriever


QUERIES: List[str] = [
    "сколько стоит Mini на 5 точек?",
    "у меня 2 магазина, сейчас на Poster",
    "расскажите про Mini",
    "а интеграции?",
    "нужен переход с r-keeper",
    "чем вы лучше iiko?",
    "есть ли интеграция с 1С?",
    "как работает офлайн режим?",
    "нужен ли ОФД?",
    "есть ли мобильное приложение?",
    "как вести инвентаризацию?",
    "можно ли принимать Kaspi QR?",
    "тариф Lite что включает?",
    "сколько стоит Standard в год?",
    "есть рассрочка?",
    "можно для сети из 10 точек?",
    "у нас кофейня, нужен учет остатков",
    "нужна касса для аптеки и маркировка",
    "система для общепита с кухней",
    "как обучаете кассиров?",
    "какой срок внедрения?",
    "работаете в Алматы?",
    "хочу перейти с umag",
    "у меня 3 кассира, как ограничить права доступа?",
    "как выгрузить отчеты в Excel?",
    "нужна синхронизация с маркетплейсами",
    "интересуют отличия тарифов Mini Lite Standard",
    "сколько стоит комплект оборудования?",
    "можно ли работать без интернета и пробивать чеки?",
    "интересует Wipon Desktop и Wipon Kassa, в чем разница?",
]


@dataclass
class QueryABResult:
    query: str
    before_latency_ms: float
    after_latency_ms: float
    before_keys: List[str]
    after_keys: List[str]
    before_stages: List[str]
    after_stages: List[str]
    before_snippets: List[str]
    after_snippets: List[str]
    overlap_at_5: int
    added_keys: List[str]
    removed_keys: List[str]


def _to_key(result: SearchResult) -> str:
    return f"{result.section.category}/{result.section.topic}"


def _snippet(result: SearchResult, max_len: int = 140) -> str:
    text = (result.section.facts or "").replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _legacy_short_circuit_search(retriever, query: str, top_k: int) -> List[SearchResult]:
    if not query or not query.strip():
        return []
    sections = retriever.kb.sections

    if retriever.use_embeddings and retriever.embedder:
        semantic_results = retriever._semantic_search(query, sections, top_k=top_k)
        if semantic_results:
            return semantic_results

    exact_results = retriever._exact_search(query, sections)
    if exact_results:
        return exact_results[:top_k]

    lemma_results = retriever._lemma_search(query, sections)
    if lemma_results:
        return lemma_results[:top_k]

    return []


def _run_query_ab(retriever, query: str, top_k: int = 5) -> QueryABResult:
    t0 = time.perf_counter()
    before_results = _legacy_short_circuit_search(retriever, query, top_k=top_k)
    before_latency_ms = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    after_results = retriever.search(query, top_k=top_k)
    after_latency_ms = (time.perf_counter() - t1) * 1000

    before_keys = [_to_key(r) for r in before_results]
    after_keys = [_to_key(r) for r in after_results]
    before_set = set(before_keys)
    after_set = set(after_keys)

    return QueryABResult(
        query=query,
        before_latency_ms=round(before_latency_ms, 2),
        after_latency_ms=round(after_latency_ms, 2),
        before_keys=before_keys,
        after_keys=after_keys,
        before_stages=[r.stage.value for r in before_results],
        after_stages=[r.stage.value for r in after_results],
        before_snippets=[_snippet(r) for r in before_results],
        after_snippets=[_snippet(r) for r in after_results],
        overlap_at_5=len(before_set & after_set),
        added_keys=sorted(after_set - before_set),
        removed_keys=sorted(before_set - after_set),
    )


def main() -> None:
    print("=" * 80)
    print("Retrieval A/B benchmark: legacy short-circuit vs hybrid RRF")
    print(f"Queries: {len(QUERIES)}")
    print("=" * 80)

    retriever = get_retriever(use_embeddings=True)
    top_k = 5
    per_query: List[QueryABResult] = []

    for idx, query in enumerate(QUERIES, start=1):
        result = _run_query_ab(retriever, query, top_k=top_k)
        per_query.append(result)
        changed = result.before_keys != result.after_keys
        print(
            f"[{idx:02d}/{len(QUERIES)}] "
            f"changed={str(changed):5s} "
            f"overlap@5={result.overlap_at_5} "
            f"before={result.before_latency_ms:.1f}ms "
            f"after={result.after_latency_ms:.1f}ms "
            f"q={query}"
        )

    changed_count = sum(1 for item in per_query if item.before_keys != item.after_keys)
    avg_overlap = sum(item.overlap_at_5 for item in per_query) / max(len(per_query), 1)
    avg_before_latency = sum(item.before_latency_ms for item in per_query) / max(len(per_query), 1)
    avg_after_latency = sum(item.after_latency_ms for item in per_query) / max(len(per_query), 1)
    before_empty = sum(1 for item in per_query if not item.before_keys)
    after_empty = sum(1 for item in per_query if not item.after_keys)

    summary = {
        "queries_total": len(per_query),
        "top_k": top_k,
        "queries_changed_top5": changed_count,
        "queries_changed_top5_rate": round(changed_count / max(len(per_query), 1), 4),
        "avg_overlap_at_5": round(avg_overlap, 4),
        "avg_before_latency_ms": round(avg_before_latency, 2),
        "avg_after_latency_ms": round(avg_after_latency, 2),
        "before_empty_results": before_empty,
        "after_empty_results": after_empty,
    }

    payload = {
        "summary": summary,
        "queries": [asdict(item) for item in per_query],
    }

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_path = os.path.join(repo_root, "results", "benchmark_retrieval_ab.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("\nSummary:")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
