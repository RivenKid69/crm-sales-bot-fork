#!/usr/bin/env python3
"""
Benchmark: подбор оптимального semantic_threshold для FRIDA.

Прогоняет CascadeRetriever._semantic_search() напрямую
на наборе типичных запросов с известными ожидаемыми секциями.
Перебирает threshold от 0.20 до 0.70 с шагом 0.05.

FRIDA работает на CPU (device="cpu").
"""

import sys, os, time, json
# GPU for fast benchmarking

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import dataclass, field
from typing import List, Dict, Tuple
from collections import defaultdict

from src.knowledge.loader import load_knowledge_base
from src.knowledge.retriever import CascadeRetriever, MatchStage

# ─── Test cases ───────────────────────────────────────────────────────────
# (query, expected_topic_substrings, group)
# hit = хотя бы 1 результат из top_k содержит ожидаемый substring в category/topic

@dataclass
class TC:
    query: str
    expected: List[str]   # substring в f"{section.category}/{section.topic}"
    group: str

TESTS: List[TC] = [
    # ── PRICING ──
    TC("Сколько стоит ваша система?", ["pricing"], "Pricing"),
    TC("Какие тарифы у вас есть?", ["pricing", "tariff"], "Pricing"),
    TC("цена за 5 точек", ["pricing", "multistore"], "Pricing"),
    TC("стоимость на 10 касс", ["pricing", "tariff"], "Pricing"),
    TC("есть ли бесплатная версия?", ["pricing", "free"], "Pricing"),
    TC("рассрочка есть?", ["pricing", "payment", "installment"], "Pricing"),
    TC("почём самый дешёвый тариф?", ["pricing", "mini"], "Pricing"),
    TC("какая стоимость подключения?", ["pricing"], "Pricing"),

    # ── FEATURES ──
    TC("какие отчёты можно строить?", ["analytics"], "Features"),
    TC("как работает учёт товаров?", ["inventory"], "Features"),
    TC("можно ли управлять сотрудниками?", ["employees"], "Features"),
    TC("есть ли мобильное приложение?", ["mobile"], "Features"),
    TC("какие функции у кассы?", ["features", "cashier", "pos", "kassa"], "Features"),
    TC("как настроить систему лояльности?", ["promotions", "loyalty", "bonus", "discount"], "Features"),
    TC("работает ли с маркировкой товаров?", ["marking", "integrations"], "Features"),
    TC("как вести инвентаризацию?", ["inventory"], "Features"),
    TC("можно ли импортировать товары из Excel?", ["inventory", "import", "excel"], "Features"),

    # ── INTEGRATIONS ──
    TC("интеграция с 1С есть?", ["1c", "integrations"], "Integrations"),
    TC("работает ли с Kaspi?", ["kaspi"], "Integrations"),
    TC("можно ли подключить эквайринг?", ["payment", "acquiring", "terminal", "bank"], "Integrations"),
    TC("есть ли интеграция с маркетплейсами?", ["marketplace"], "Integrations"),

    # ── SUPPORT ──
    TC("как обучить сотрудников работе с системой?", ["support", "training", "onboarding"], "Support"),
    TC("есть ли техническая поддержка 24/7?", ["support"], "Support"),
    TC("как быстро внедряется система?", ["support", "implement", "onboarding", "connection"], "Support"),
    TC("что делать если система сломалась?", ["support", "stability"], "Support"),

    # ── EQUIPMENT ──
    TC("какое оборудование нужно?", ["equipment"], "Equipment"),
    TC("подходит ли обычный принтер чеков?", ["equipment", "printer"], "Equipment"),
    TC("нужен ли сканер штрих-кодов?", ["equipment", "scanner"], "Equipment"),

    # ── FISCAL ──
    TC("как работает фискализация?", ["fiscal"], "Fiscal"),
    TC("нужен ли ККМ?", ["fiscal", "tis"], "Fiscal"),
    TC("как отправлять чеки в ОФД?", ["fiscal", "ofd"], "Fiscal"),

    # ── COMPETITORS ──
    TC("чем вы лучше iiko?", ["competitors", "iiko"], "Competitors"),
    TC("чем отличается от umag?", ["competitors", "umag"], "Competitors"),
    TC("почему стоит выбрать wipon?", ["competitors", "why"], "Competitors"),

    # ── PRODUCTS ──
    TC("какие продукты у вас есть?", ["products"], "Products"),
    TC("что такое Wipon Desktop?", ["desktop", "products"], "Products"),
    TC("расскажите про Wipon Kassa", ["kassa", "products"], "Products"),

    # ── REGIONS ──
    TC("работаете ли вы в Алматы?", ["regions"], "Regions"),
    TC("доставляете ли в регионы?", ["regions"], "Regions"),

    # ── TIS ──
    TC("что такое ТИС?", ["tis"], "TIS"),
    TC("какой налоговый режим мне выбрать?", ["tis", "retail"], "TIS"),
    TC("нужно ли мне СНТ?", ["snt", "fiscal"], "TIS"),

    # ── STABILITY ──
    TC("что будет если интернет пропадёт?", ["stability", "offline"], "Stability"),
    TC("насколько надёжна ваша система?", ["stability"], "Stability"),

    # ── TRICKY ──
    TC("мне нужна автоматизация магазина", ["products", "overview", "features"], "Tricky"),
    TC("а если у меня сеть магазинов?", ["pricing", "multistore", "network", "faq"], "Tricky"),
    TC("қандай бағалар бар?", ["pricing", "tariff"], "Tricky-KZ"),
    TC("жүйе қанша тұрады?", ["pricing", "tariff"], "Tricky-KZ"),
    TC("Мне нужно учёт товаров вести", ["inventory"], "Tricky"),
    TC("какая СУБД используется?", ["support", "stability", "db"], "Tricky"),
    TC("можно ли платить через Kaspi QR?", ["kaspi", "payment"], "Tricky"),
    TC("ваша система работает на планшете?", ["mobile", "tablet"], "Tricky"),
]


def matches(key: str, patterns: List[str]) -> bool:
    key_l = key.lower()
    return any(p.lower() in key_l for p in patterns)


def run_at_threshold(retriever: CascadeRetriever, threshold: float, top_k: int = 3):
    """Run all tests at a given semantic_threshold, return metrics."""
    retriever.semantic_threshold = threshold

    hits = 0
    mrr_sum = 0.0
    total = len(TESTS)
    group_hits: Dict[str, int] = defaultdict(int)
    group_total: Dict[str, int] = defaultdict(int)
    misses = []
    scores_on_hit = []
    scores_on_miss = []

    for tc in TESTS:
        group_total[tc.group] += 1
        # run semantic search directly
        results = retriever._semantic_search(tc.query, retriever.kb.sections, top_k)

        hit = False
        mrr_val = 0.0
        for rank, r in enumerate(results, 1):
            key = f"{r.section.category}/{r.section.topic}"
            if matches(key, tc.expected):
                if not hit:
                    mrr_val = 1.0 / rank
                hit = True
                scores_on_hit.append(r.score)
                break

        if not hit and results:
            scores_on_miss.append(results[0].score)

        if hit:
            hits += 1
            group_hits[tc.group] += 1
            mrr_sum += mrr_val
        else:
            misses.append((tc, [f"{r.section.category}/{r.section.topic}:{r.score:.3f}" for r in results[:3]]))

    return {
        "threshold": threshold,
        "hit_rate": hits / total,
        "hits": hits,
        "total": total,
        "mrr": mrr_sum / total,
        "group_stats": {
            g: {"hits": group_hits.get(g, 0), "total": group_total[g],
                "rate": group_hits.get(g, 0) / group_total[g]}
            for g in sorted(group_total)
        },
        "avg_hit_score": sum(scores_on_hit) / max(len(scores_on_hit), 1),
        "min_hit_score": min(scores_on_hit) if scores_on_hit else 0,
        "avg_miss_top_score": sum(scores_on_miss) / max(len(scores_on_miss), 1),
        "misses": misses,
    }


def main():
    print("=" * 70)
    print("  FRIDA THRESHOLD BENCHMARK")
    print("  Semantic search quality at different threshold values")
    print("=" * 70)

    # Load KB + init embeddings
    print("\n[1] Loading KB + FRIDA embeddings (GPU)...")
    t0 = time.perf_counter()
    kb = load_knowledge_base()
    # Force GPU for benchmark speed
    from src.settings import settings as _s
    _s.retriever.embedder_device = "cuda"
    retriever = CascadeRetriever(knowledge_base=kb, use_embeddings=True)
    init_time = time.perf_counter() - t0
    print(f"    {len(kb.sections)} sections indexed in {init_time:.1f}s")
    print(f"    Embedder: {retriever.embedder}")
    print(f"    Prefixes: {retriever._use_prefixes}")

    # Warmup
    print("\n[2] Warmup (1 query)...")
    retriever._semantic_search("тест", retriever.kb.sections, 3)

    # Sweep thresholds
    thresholds = [round(0.20 + i * 0.05, 2) for i in range(11)]  # 0.20 .. 0.70
    all_results = []

    print(f"\n[3] Running {len(TESTS)} queries × {len(thresholds)} thresholds...\n")

    for th in thresholds:
        t0 = time.perf_counter()
        res = run_at_threshold(retriever, th, top_k=3)
        elapsed = (time.perf_counter() - t0) * 1000
        res["time_ms"] = round(elapsed, 0)
        all_results.append(res)

        bar = "█" * int(res["hit_rate"] * 30) + "░" * (30 - int(res["hit_rate"] * 30))
        print(f"  th={th:.2f}  {bar}  {res['hits']:2d}/{res['total']}  "
              f"HR={res['hit_rate']:.1%}  MRR={res['mrr']:.3f}  "
              f"avg_hit={res['avg_hit_score']:.3f}  min_hit={res['min_hit_score']:.3f}  "
              f"{res['time_ms']:.0f}ms")

    # Find best
    best = max(all_results, key=lambda r: (r["hit_rate"], r["mrr"]))
    print(f"\n{'=' * 70}")
    print(f"  BEST THRESHOLD: {best['threshold']:.2f}")
    print(f"  Hit Rate: {best['hit_rate']:.1%}  MRR: {best['mrr']:.3f}")
    print(f"  Min hit score: {best['min_hit_score']:.3f}")
    print(f"{'=' * 70}")

    # Print group breakdown for best
    print(f"\n  Per-group at threshold={best['threshold']:.2f}:")
    for g, gs in sorted(best["group_stats"].items()):
        bar = "█" * int(gs["rate"] * 20) + "░" * (20 - int(gs["rate"] * 20))
        print(f"    {g:15s}  {bar}  {gs['hits']}/{gs['total']} ({gs['rate']:.0%})")

    # Print misses for best
    if best["misses"]:
        print(f"\n  MISSES at threshold={best['threshold']:.2f} ({len(best['misses'])}):")
        for tc, got in best["misses"]:
            print(f"    ✗ [{tc.group}] {tc.query}")
            print(f"      Expected: {tc.expected}")
            print(f"      Got: {got}")

    # Also show scores distribution for recommended threshold
    # to help pick threshold just below min_hit_score
    print(f"\n  RECOMMENDATION:")
    # Find the highest threshold that still has >=90% hit rate
    for r in sorted(all_results, key=lambda x: -x["threshold"]):
        if r["hit_rate"] >= 0.90:
            print(f"    Highest threshold with ≥90% HR: {r['threshold']:.2f} "
                  f"(HR={r['hit_rate']:.1%}, MRR={r['mrr']:.3f})")
            break
    for r in sorted(all_results, key=lambda x: -x["threshold"]):
        if r["hit_rate"] >= 0.85:
            print(f"    Highest threshold with ≥85% HR: {r['threshold']:.2f} "
                  f"(HR={r['hit_rate']:.1%}, MRR={r['mrr']:.3f})")
            break
    for r in sorted(all_results, key=lambda x: -x["threshold"]):
        if r["hit_rate"] >= 0.80:
            print(f"    Highest threshold with ≥80% HR: {r['threshold']:.2f} "
                  f"(HR={r['hit_rate']:.1%}, MRR={r['mrr']:.3f})")
            break

    # Save JSON
    out_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "results", "benchmark_frida_threshold.json"
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    save_data = {
        "best_threshold": best["threshold"],
        "init_time_s": round(init_time, 1),
        "sections": len(kb.sections),
        "test_count": len(TESTS),
        "results": [
            {
                "threshold": r["threshold"],
                "hit_rate": round(r["hit_rate"], 4),
                "mrr": round(r["mrr"], 4),
                "hits": r["hits"],
                "total": r["total"],
                "avg_hit_score": round(r["avg_hit_score"], 4),
                "min_hit_score": round(r["min_hit_score"], 4),
                "avg_miss_top_score": round(r["avg_miss_top_score"], 4),
                "group_stats": r["group_stats"],
                "time_ms": r["time_ms"],
            }
            for r in all_results
        ],
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)
    print(f"\n  Saved: {out_path}")


if __name__ == "__main__":
    main()
