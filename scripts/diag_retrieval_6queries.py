#!/usr/bin/env python3
"""
Diagnostic: run retrieval for the 6 failing queries and show per-stage rankings.
Usage: python scripts/diag_retrieval_6queries.py
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.knowledge.retriever import get_retriever

QUERIES = [
    ("D02-T8", "Отвечали по 3 дня"),
    ("D06-T7", "Kaspi маркетплейсом интеграция?"),
    ("D06-T10", "Настройку оборудования удалённо или выезжаете?"),
    ("D07-T7", "Интеграция с WhatsApp?"),
    ("D07-T8", "Что реально есть для розничного?"),
    ("D04-T5", "Сколько это стоит?"),
]

def main():
    retriever = get_retriever()
    kb_sections = retriever.kb.sections

    results_all = []

    for tag, query in QUERIES:
        print(f"\n{'='*80}")
        print(f"  {tag}: \"{query}\"")
        print(f"{'='*80}")

        # Stage 1: Semantic
        sem = retriever._semantic_search(query, kb_sections, top_k=10)
        # Stage 2: Exact keyword
        exact = retriever._exact_search(query, kb_sections)
        # Stage 3: Lemma
        lemma = retriever._lemma_search(query, kb_sections)
        # RRF merge
        rrf = retriever._rrf_merge([sem, exact, lemma], k=60)[:10]

        entry = {"tag": tag, "query": query, "stages": {}}

        print(f"\n  --- SEMANTIC (top 10) ---")
        sem_list = []
        for i, r in enumerate(sem[:10]):
            key = f"{r.section.category}/{r.section.topic}"
            print(f"    #{i+1}  score={r.score:.4f}  {key}")
            sem_list.append({"rank": i+1, "score": round(r.score, 4), "key": key})
        entry["stages"]["semantic"] = sem_list

        print(f"\n  --- EXACT KEYWORD (all matches, sorted by score) ---")
        exact_sorted = sorted(exact, key=lambda r: r.score, reverse=True)
        ex_list = []
        for i, r in enumerate(exact_sorted[:10]):
            key = f"{r.section.category}/{r.section.topic}"
            kw = ", ".join(r.matched_keywords or [])
            print(f"    #{i+1}  score={r.score:.2f}  {key}  kw=[{kw}]")
            ex_list.append({"rank": i+1, "score": round(r.score, 2), "key": key, "matched_kw": r.matched_keywords or []})
        if not exact_sorted:
            print("    (no matches)")
        entry["stages"]["exact"] = ex_list

        print(f"\n  --- LEMMA (top 10) ---")
        lem_list = []
        for i, r in enumerate(lemma[:10]):
            key = f"{r.section.category}/{r.section.topic}"
            lm = ", ".join(r.matched_lemmas or [])
            print(f"    #{i+1}  score={r.score:.4f}  {key}  lemmas=[{lm}]")
            lem_list.append({"rank": i+1, "score": round(r.score, 4), "key": key, "matched_lemmas": r.matched_lemmas or []})
        entry["stages"]["lemma"] = lem_list

        print(f"\n  --- RRF MERGED (top 10) ---")
        rrf_list = []
        for i, r in enumerate(rrf[:10]):
            key = f"{r.section.category}/{r.section.topic}"
            print(f"    #{i+1}  rrf={r.score:.5f}  stage={r.stage.value}  {key}")
            rrf_list.append({"rank": i+1, "rrf_score": round(r.score, 5), "stage": r.stage.value, "key": key})
        entry["stages"]["rrf"] = rrf_list

        results_all.append(entry)

    # Save JSON
    out_path = "results/diag_retrieval_6queries.json"
    os.makedirs("results", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results_all, f, ensure_ascii=False, indent=2)
    print(f"\n\nSaved to {out_path}")

if __name__ == "__main__":
    main()
