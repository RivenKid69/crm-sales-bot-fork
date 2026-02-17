#!/usr/bin/env python3
"""
Full E2E Audit: Enhanced Autonomous Retrieval → LLM Generation.

200 complex queries through the FULL pipeline:
  Query → EnhancedRetrievalPipeline → ResponseGenerator → LLM → Final Answer

For each query shows:
  1. Retrieved facts (sections, count)
  2. Final LLM response
  3. Quality check: expected markers in response/facts

Usage:
  python tests/e2e_full_pipeline_audit.py           # all 200
  python tests/e2e_full_pipeline_audit.py --compact  # compact output (summary only)
  python tests/e2e_full_pipeline_audit.py --from 50  # start from query 50
  python tests/e2e_full_pipeline_audit.py --to 100   # stop at query 100
"""

import sys
import os
import time
import json
import argparse
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.llm import OllamaLLM
from src.config_loader import ConfigLoader
from src.generator import ResponseGenerator
from src.knowledge.enhanced_retrieval import EnhancedRetrievalPipeline
from src.knowledge.retriever import get_retriever

from tests.e2e_200_queries import QUERIES


def evaluate_quality(response, facts, expect_markers):
    """Evaluate response quality based on expected markers."""
    response_lower = response.lower()
    facts_lower = (facts or "").lower()

    markers_found = []
    markers_missing = []
    for marker in expect_markers:
        if marker.lower() in response_lower or marker.lower() in facts_lower:
            markers_found.append(marker)
        else:
            markers_missing.append(marker)

    if not expect_markers:
        quality = "N/A"
    elif not markers_missing:
        quality = "OK"
    elif len(markers_found) >= len(expect_markers) * 0.5:
        quality = "PARTIAL"
    else:
        quality = "FAIL"

    # Hallucination / red flags
    flags = []
    red_phrases = [
        "к сожалению, у меня нет информации",
        "я не могу найти",
        "информация отсутствует",
        "не нашёл данных",
    ]
    for phrase in red_phrases:
        if phrase in response_lower:
            flags.append("NO_INFO")
            break

    if len(response) < 20:
        flags.append("TOO_SHORT")
    if len(response) > 1500:
        flags.append("TOO_LONG")
    if "GENERATION ERROR" in response:
        flags.append("GEN_ERROR")
    if "RETRIEVAL ERROR" in str(facts):
        flags.append("RET_ERROR")

    return quality, markers_found, markers_missing, flags


def run_audit(args):
    """Run full e2e audit through real LLM."""
    compact = args.compact
    q_from = args.q_from - 1  # 0-indexed
    q_to = args.q_to

    queries = QUERIES[q_from:q_to]
    total_q = len(queries)

    print("=" * 80)
    print(f"  FULL E2E AUDIT: Enhanced Retrieval → LLM Generation")
    print(f"  Model: qwen3:14b | Queries: {total_q} (#{q_from+1}..#{q_from+total_q})")
    print("=" * 80)

    # ── Initialize ──
    print("\n[INIT] Loading components...")
    llm = OllamaLLM(model="qwen3:14b", base_url="http://localhost:11434", timeout=120)
    assert llm.health_check(), "Ollama not running! Run: ollama serve"

    loader = ConfigLoader()
    flow = loader.load_flow("autonomous")
    gen = ResponseGenerator(llm, flow=flow)
    retriever = get_retriever()
    kb = retriever.kb
    pipeline = EnhancedRetrievalPipeline(llm=llm, category_router=None)

    print(f"[INIT] KB: {len(kb.sections)} sections, {len(set(s.category for s in kb.sections))} categories")
    print(f"[INIT] Ready. Starting audit...\n")

    results = []
    total_start = time.time()

    for idx, q in enumerate(queries):
        qid = q["id"]
        query = q["query"]
        state = q["state"]
        intent = q["intent"]
        history = q.get("history") or []
        expect_markers = q["expect_markers"]
        category = q["category"]
        progress = f"[{idx+1}/{total_q}]"

        # ── Step 1: Retrieval ──
        t0 = time.perf_counter()
        try:
            facts, urls, fact_keys = pipeline.retrieve(
                user_message=query, intent=intent, state=state,
                flow_config=flow, kb=kb, recently_used_keys=set(),
                history=history,
            )
        except Exception as e:
            facts, urls, fact_keys = f"RETRIEVAL ERROR: {e}", [], []
        retrieval_ms = (time.perf_counter() - t0) * 1000

        facts_chars = len(facts) if isinstance(facts, str) else 0

        # ── Step 2: LLM Generation ──
        context = {
            "user_message": query,
            "intent": intent,
            "state": state,
            "history": history,
            "collected_data": {},
            "missing_data": ["company_size", "business_type"],
            "goal": flow.states.get(state, {}).get("goal", ""),
            "spin_phase": flow.states.get(state, {}).get("phase", ""),
            "recent_fact_keys": [],
        }

        t1 = time.perf_counter()
        try:
            response = gen.generate("autonomous_respond", context)
        except Exception as e:
            response = f"GENERATION ERROR: {e}"
        generation_ms = (time.perf_counter() - t1) * 1000
        total_ms = retrieval_ms + generation_ms

        # ── Step 3: Evaluate ──
        quality, markers_found, markers_missing, flags = evaluate_quality(
            response, facts, expect_markers
        )

        emoji = {"OK": "✅", "PARTIAL": "🟡", "FAIL": "❌", "N/A": "⚪"}.get(quality, "?")

        # ── Output ──
        if compact:
            flag_str = f" ⚠{flags}" if flags else ""
            miss_str = f" miss={markers_missing}" if markers_missing else ""
            print(f"  {progress} Q{qid:03d} {emoji} {quality:<7} {total_ms:5.0f}ms  {category:<30} {query[:50]}{miss_str}{flag_str}")
        else:
            print(f"\n{'─' * 80}")
            print(f"  {progress} Q{qid:03d} [{category}]")
            print(f"  State: {state} | Intent: {intent}")
            print(f"  Query: {query}")
            if history:
                print(f"  History: {len(history)} turns")

            # Retrieved facts
            if fact_keys:
                top_keys = fact_keys[:6]
                print(f"\n  Retrieved {len(fact_keys)} sections ({retrieval_ms:.0f}ms): {', '.join(top_keys)}", end="")
                if len(fact_keys) > 6:
                    print(f" +{len(fact_keys)-6} more", end="")
                print()
            else:
                print(f"\n  No facts retrieved ({retrieval_ms:.0f}ms)")
            print(f"  Facts: {facts_chars} chars (~{facts_chars//4} tokens)")

            # LLM response
            resp_display = response.replace('\n', ' ')
            if len(resp_display) > 200:
                resp_display = resp_display[:200] + "..."
            print(f"\n  LLM ({generation_ms:.0f}ms): {resp_display}")

            # Quality
            print(f"\n  {emoji} {quality}", end="")
            if markers_found:
                print(f"  found={markers_found}", end="")
            if markers_missing:
                print(f"  MISSING={markers_missing}", end="")
            if flags:
                print(f"  FLAGS={flags}", end="")
            print(f"  [{total_ms:.0f}ms]")

        results.append({
            "id": qid,
            "category": category,
            "query": query,
            "state": state,
            "intent": intent,
            "fact_keys": fact_keys[:10],  # cap for JSON size
            "facts_sections": len(fact_keys),
            "facts_chars": facts_chars,
            "response": response,
            "response_len": len(response),
            "quality": quality,
            "markers_found": markers_found,
            "markers_missing": markers_missing,
            "hallucination_flags": flags,
            "retrieval_ms": round(retrieval_ms),
            "generation_ms": round(generation_ms),
            "total_ms": round(total_ms),
        })

    # ═══════════════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════════════
    total_time = time.time() - total_start

    ok = sum(1 for r in results if r["quality"] == "OK")
    partial = sum(1 for r in results if r["quality"] == "PARTIAL")
    fail = sum(1 for r in results if r["quality"] == "FAIL")
    na = sum(1 for r in results if r["quality"] == "N/A")
    scored = [r for r in results if r["quality"] != "N/A"]

    print("\n" + "=" * 80)
    print("  SUMMARY")
    print("=" * 80)
    print(f"\n  Total: {len(results)} queries in {total_time:.1f}s")
    print(f"  ✅ OK:      {ok}")
    print(f"  🟡 PARTIAL: {partial}")
    print(f"  ❌ FAIL:    {fail}")
    print(f"  ⚪ N/A:     {na}")
    if scored:
        acc = ok / len(scored) * 100
        acc_with_partial = (ok + partial) / len(scored) * 100
        print(f"\n  Strict accuracy  (OK only):     {ok}/{len(scored)} = {acc:.1f}%")
        print(f"  Relaxed accuracy (OK+PARTIAL):  {ok+partial}/{len(scored)} = {acc_with_partial:.1f}%")

    avg_ret = sum(r["retrieval_ms"] for r in results) / len(results)
    avg_gen = sum(r["generation_ms"] for r in results) / len(results)
    avg_tot = sum(r["total_ms"] for r in results) / len(results)
    p95_tot = sorted(r["total_ms"] for r in results)[int(len(results) * 0.95)]

    print(f"\n  Latency:")
    print(f"    Avg retrieval:  {avg_ret:.0f}ms")
    print(f"    Avg generation: {avg_gen:.0f}ms")
    print(f"    Avg total:      {avg_tot:.0f}ms")
    print(f"    P95 total:      {p95_tot:.0f}ms")

    # ── Per-category breakdown ──
    cat_stats = defaultdict(lambda: {"ok": 0, "partial": 0, "fail": 0, "na": 0, "total": 0})
    quality_map = {"OK": "ok", "PARTIAL": "partial", "FAIL": "fail", "N/A": "na"}
    for r in results:
        cat = r["category"].split("_")[0]  # group prefix
        cat_stats[cat]["total"] += 1
        cat_stats[cat][quality_map.get(r["quality"], "na")] += 1

    print(f"\n  Per-category group:")
    print(f"  {'Category':<25} {'Total':>5} {'OK':>4} {'PART':>4} {'FAIL':>4} {'N/A':>4} {'Rate':>6}")
    print(f"  {'─'*25} {'─'*5} {'─'*4} {'─'*4} {'─'*4} {'─'*4} {'─'*6}")
    for cat in sorted(cat_stats.keys()):
        s = cat_stats[cat]
        scorable = s["ok"] + s["partial"] + s["fail"]
        rate = f"{s['ok']/scorable*100:.0f}%" if scorable > 0 else "N/A"
        print(f"  {cat:<25} {s['total']:>5} {s['ok']:>4} {s['partial']:>4} {s['fail']:>4} {s['na']:>4} {rate:>6}")

    # ── Problems detail ──
    problems = [r for r in results if r["quality"] in ("PARTIAL", "FAIL")]
    if problems:
        print(f"\n  {'─' * 70}")
        print(f"  PROBLEMS ({len(problems)}):")
        for r in problems:
            print(f"    Q{r['id']:03d} [{r['quality']}] {r['query'][:65]}")
            if r["markers_missing"]:
                print(f"          Missing: {r['markers_missing']}")
            resp_short = r["response"].replace('\n', ' ')[:120]
            print(f"          Response: {resp_short}")

    # ── Flagged ──
    flagged = [r for r in results if r["hallucination_flags"]]
    if flagged:
        print(f"\n  {'─' * 70}")
        print(f"  FLAGGED ({len(flagged)}):")
        for r in flagged:
            print(f"    Q{r['id']:03d} {r['hallucination_flags']}  {r['query'][:60]}")

    # ── Save JSON ──
    output_path = os.path.join(os.path.dirname(__file__), "e2e_audit_results_200.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n  Results saved to: {output_path}")
    print("=" * 80)

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Full E2E Pipeline Audit")
    parser.add_argument("--compact", action="store_true", help="Compact output (one line per query)")
    parser.add_argument("--from", dest="q_from", type=int, default=1, help="Start from query N (1-indexed)")
    parser.add_argument("--to", dest="q_to", type=int, default=None, help="Stop at query N")
    args = parser.parse_args()
    if args.q_to is None:
        args.q_to = len(QUERIES)
    run_audit(args)
