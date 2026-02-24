#!/usr/bin/env python3
"""
Benchmark: Current KB keywords vs Cleaned KB keywords.

Cleaning strategy:
  1. Remove cross-category duplicate keywords (keep only in "home" category)
  2. Cap keywords per section at MAX_KW (keep longest/most specific first)
  3. Remove very generic 1-word keywords that appear in 10+ sections

Both run through CascadeRetriever Stage 1+2 (keywords only, no embeddings)
— same as production autonomous flow.
"""

import sys, os, time, json, copy
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.knowledge.loader import load_knowledge_base
from src.knowledge.base import KnowledgeBase, KnowledgeSection
from src.knowledge.retriever import CascadeRetriever, SearchResult, MatchStage


MAX_KW_PER_SECTION = 12  # Target cap (from ~14 avg)


# ─── Test cases (same as full benchmark) ──────────────────────────────────────

@dataclass
class TC:
    query: str
    expected: List[str]
    group: str
    desc: str

TESTS: List[TC] = [
    # PRICING
    TC("Сколько стоит ваша система?", ["tariffs", "pricing_tariff"], "Pricing", "Прямой вопрос о цене"),
    TC("Какие тарифы у вас есть?", ["tariffs", "pricing_tariff"], "Pricing", "Тарифы"),
    TC("цена за 5 точек", ["pricing_multistore", "pricing_5", "tariffs"], "Pricing", "Цена 5 точек"),
    TC("стоимость на 10 касс", ["tariffs", "pricing_tariff", "pricing_multistore"], "Pricing", "Стоимость 10 касс"),
    TC("есть ли бесплатная версия?", ["free", "pricing_free", "pricing_trial"], "Pricing", "Бесплатная версия"),
    TC("рассрочка есть?", ["pricing_installment", "pricing_payment"], "Pricing", "Рассрочка"),
    TC("почём самый дешёвый тариф?", ["tariffs", "pricing_tariff_mini", "products_wipon_mini"], "Pricing", "Дешёвый тариф"),
    # FEATURES
    TC("какие отчёты можно строить?", ["analytics_", "reports"], "Features", "Отчёты"),
    TC("как работает учёт товаров?", ["inventory_"], "Features", "Учёт товаров"),
    TC("можно ли управлять сотрудниками?", ["employees_"], "Features", "Сотрудники"),
    TC("есть ли мобильное приложение?", ["mobile_app", "mobile_"], "Features", "Мобильное приложение"),
    TC("какие функции у кассы?", ["features_cashier", "features_pos", "wipon_kassa"], "Features", "Функции кассы"),
    TC("как настроить систему лояльности?", ["promotions_loyalty", "promotions_bonus", "promotions_discount"], "Features", "Лояльность"),
    TC("работает ли с маркировкой товаров?", ["integrations_marking", "marking"], "Features", "Маркировка"),
    # INTEGRATIONS
    TC("интеграция с 1С есть?", ["1c", "integrations_1c"], "Integrations", "1С"),
    TC("работает ли с Kaspi?", ["kaspi"], "Integrations", "Kaspi"),
    TC("можно ли подключить эквайринг?", ["integrations_bank", "tis_pos_terminal", "payment", "acquiring"], "Integrations", "Эквайринг"),
    TC("есть ли интеграция с маркетплейсами?", ["marketplace", "wildberries"], "Integrations", "Маркетплейсы"),
    # SUPPORT
    TC("как обучить сотрудников работе с системой?", ["support_training", "support_onboarding"], "Support", "Обучение"),
    TC("есть ли техническая поддержка 24/7?", ["support_sla", "support_channel", "help"], "Support", "Поддержка 24/7"),
    TC("как быстро внедряется система?", ["support_implement", "support_onboarding", "tis_connection_speed"], "Support", "Внедрение"),
    TC("что делать если система сломалась?", ["support_broken", "stability_"], "Support", "Сломалась"),
    # EQUIPMENT
    TC("какое оборудование нужно?", ["equipment_"], "Equipment", "Оборудование"),
    TC("подходит ли обычный принтер чеков?", ["equipment_", "printer"], "Equipment", "Принтер чеков"),
    TC("нужен ли сканер штрих-кодов?", ["equipment_", "scanner", "barcode"], "Equipment", "Сканер"),
    # FISCAL
    TC("как работает фискализация?", ["fiscal_"], "Fiscal", "Фискализация"),
    TC("нужен ли ККМ?", ["fiscal_", "tis_"], "Fiscal", "ККМ"),
    TC("как отправлять чеки в ОФД?", ["fiscal_ofd", "fiscal_receipt", "fiscal_send"], "Fiscal", "ОФД"),
    # COMPETITORS
    TC("чем вы лучше iiko?", ["vs_others", "competitors_", "iiko"], "Competitors", "iiko"),
    TC("чем отличается от umag?", ["competitors_umag", "umag"], "Competitors", "umag"),
    TC("почему стоит выбрать wipon?", ["competitors_general", "vs_others", "why_wipon"], "Competitors", "Почему Wipon"),
    # PRODUCTS
    TC("какие продукты у вас есть?", ["products_wipon", "overview", "products_what"], "Products", "Продукты"),
    TC("что такое Wipon Desktop?", ["wipon_desktop", "products_desktop"], "Products", "Desktop"),
    TC("расскажите про Wipon Kassa", ["wipon_kassa", "products_kassa"], "Products", "Kassa"),
    # REGIONS
    TC("работаете ли вы в Алматы?", ["regions_", "coverage"], "Regions", "Алматы"),
    TC("доставляете ли в регионы?", ["regions_delivery"], "Regions", "Доставка"),
    # TIS
    TC("что такое ТИС?", ["tis_"], "TIS", "Что такое ТИС"),
    TC("какой налоговый режим мне выбрать?", ["tis_retail", "tis_earning", "tis_too"], "TIS", "Налоговый режим"),
    TC("нужно ли мне СНТ?", ["snt", "fiscal_document"], "TIS", "СНТ"),
    TC("как подключить ЭСФ?", ["esf", "fiscal_document"], "TIS", "ЭСФ"),
    # STABILITY
    TC("что будет если интернет пропадёт?", ["stability_offline", "stability_no_internet", "stability_internet"], "Stability", "Без интернета"),
    TC("насколько надёжна ваша система?", ["stability_"], "Stability", "Надёжность"),
    # TRICKY
    TC("мне нужна автоматизация магазина", ["products_wipon", "overview"], "Tricky", "Автоматизация"),
    TC("а если у меня сеть магазинов?", ["faq_network", "pricing_multistore", "multistore"], "Tricky", "Сеть магазинов"),
    TC("не стоит тратить время", [], "Tricky", "Отказ (не стоит ≠ цена)"),
    TC("у нас 5 точек по Казахстану", ["regions_", "coverage", "pricing_multistore"], "Tricky", "5 точек"),
    TC("қандай бағалар бар?", ["tariffs", "pricing_tariff", "pricing_"], "Tricky", "KZ: какие цены"),
    TC("жүйе қанша тұрады?", ["tariffs", "pricing_"], "Tricky", "KZ: сколько стоит"),
    TC("Мне нужно учёт товаров вести", ["inventory_"], "Tricky", "Мне нужно (не no_need)"),
    TC("какая СУБД используется?", ["support_db", "stability_data"], "Tricky", "СУБД"),
    TC("можно ли платить через Kaspi QR?", ["kaspi"], "Tricky", "Kaspi QR"),
    TC("ваша система работает на планшете?", ["mobile_tablet", "mobile_app", "mobile_kassa"], "Tricky", "Планшет"),
    TC("как вести инвентаризацию?", ["inventory_revision", "inventory_stocktaking"], "Tricky", "Инвентаризация"),
    TC("можно ли импортировать товары из Excel?", ["inventory_import", "features_import", "excel"], "Tricky", "Импорт Excel"),
]


# ─── KB Cleaning ──────────────────────────────────────────────────────────────

def clean_kb(kb: KnowledgeBase) -> Tuple[KnowledgeBase, dict]:
    """Create a cleaned copy with reduced keywords. Returns (cleaned_kb, stats)."""
    # Deep copy sections
    cleaned_sections = []
    for s in kb.sections:
        new_s = KnowledgeSection(
            category=s.category, topic=s.topic,
            keywords=list(s.keywords), facts=s.facts,
            priority=s.priority, urls=list(s.urls),
            sensitive=s.sensitive,
        )
        cleaned_sections.append(new_s)

    stats = {
        "original_total_kw": sum(len(s.keywords) for s in kb.sections),
        "original_avg_kw": 0,
        "sections": len(cleaned_sections),
    }
    stats["original_avg_kw"] = round(stats["original_total_kw"] / max(len(cleaned_sections), 1), 1)

    # Step 1: Build keyword → categories map
    kw_to_categories: Dict[str, Set[str]] = defaultdict(set)
    kw_to_sections: Dict[str, int] = Counter()
    for s in cleaned_sections:
        for kw in s.keywords:
            kw_lower = kw.lower().strip()
            kw_to_categories[kw_lower].add(s.category)
            kw_to_sections[kw_lower] += 1

    # Step 2: Identify cross-category keywords (appear in 3+ categories)
    cross_cat_kw = {kw for kw, cats in kw_to_categories.items() if len(cats) >= 3}

    # Step 3: Identify ultra-generic keywords (single words in 15+ sections)
    ultra_generic = {kw for kw, count in kw_to_sections.items()
                     if len(kw.split()) == 1 and count >= 15}

    # Step 4: For each section, determine "home" category for cross-cat keywords
    # Home = category where keyword appears in highest-priority section
    kw_home: Dict[str, str] = {}
    for kw in cross_cat_kw:
        best_cat = None
        best_prio = -1
        for s in cleaned_sections:
            if kw in [k.lower().strip() for k in s.keywords]:
                if s.priority > best_prio:
                    best_prio = s.priority
                    best_cat = s.category
        if best_cat:
            kw_home[kw] = best_cat

    # Step 5: Clean each section
    removed_cross = 0
    removed_generic = 0
    removed_cap = 0

    for s in cleaned_sections:
        original_len = len(s.keywords)
        new_kw = []

        for kw in s.keywords:
            kw_lower = kw.lower().strip()

            # Remove cross-category keyword if NOT in home category
            if kw_lower in cross_cat_kw:
                home = kw_home.get(kw_lower)
                if home and home != s.category:
                    removed_cross += 1
                    continue

            # Remove ultra-generic single words
            if kw_lower in ultra_generic:
                removed_generic += 1
                continue

            new_kw.append(kw)

        # Cap at MAX_KW: keep longest (most specific) first
        if len(new_kw) > MAX_KW_PER_SECTION:
            new_kw.sort(key=lambda k: len(k), reverse=True)
            removed_cap += len(new_kw) - MAX_KW_PER_SECTION
            new_kw = new_kw[:MAX_KW_PER_SECTION]

        s.keywords = new_kw

    cleaned_total = sum(len(s.keywords) for s in cleaned_sections)
    stats.update({
        "cleaned_total_kw": cleaned_total,
        "cleaned_avg_kw": round(cleaned_total / max(len(cleaned_sections), 1), 1),
        "removed_cross_category": removed_cross,
        "removed_ultra_generic": removed_generic,
        "removed_by_cap": removed_cap,
        "total_removed": stats["original_total_kw"] - cleaned_total,
        "reduction_pct": round((1 - cleaned_total / max(stats["original_total_kw"], 1)) * 100, 1),
        "cross_cat_keywords": len(cross_cat_kw),
        "ultra_generic_keywords": len(ultra_generic),
    })

    cleaned_kb = KnowledgeBase(
        company_name=kb.company_name,
        company_description=kb.company_description,
        sections=cleaned_sections,
    )
    return cleaned_kb, stats


# ─── Evaluation ───────────────────────────────────────────────────────────────

@dataclass
class QR:
    query: str
    desc: str
    group: str
    expected: List[str]
    found_topics: List[str]
    found_scores: List[float]
    found_stages: List[str]
    hit: bool
    mrr: float
    latency_ms: float


@dataclass
class MR:
    mode: str
    total: int = 0
    hits: int = 0
    mrr_sum: float = 0.0
    latency_sum: float = 0.0
    empty: int = 0
    per_query: List[QR] = field(default_factory=list)
    group_hits: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    group_total: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    stage_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    @property
    def hit_rate(self): return self.hits / max(self.total, 1)
    @property
    def mrr(self): return self.mrr_sum / max(self.total, 1)
    @property
    def avg_latency(self): return self.latency_sum / max(self.total, 1)


def run_eval(retriever: CascadeRetriever, mode: str, top_k: int = 5) -> MR:
    r = MR(mode=mode)
    for tc in TESTS:
        r.total += 1
        r.group_total[tc.group] += 1

        t0 = time.perf_counter()
        results = retriever.search(tc.query, top_k=top_k)
        lat = (time.perf_counter() - t0) * 1000

        topics = [x.section.topic for x in results]
        scores = [round(x.score, 4) for x in results]
        stages = [x.stage.value for x in results]
        stage = stages[0] if stages else "none"

        if not tc.expected:
            hit, mrr_val = True, 1.0
        else:
            hit, mrr_val = False, 0.0
            for rank, t in enumerate(topics, 1):
                if any(p.lower() in t.lower() for p in tc.expected):
                    mrr_val = 1.0 / rank
                    hit = True
                    break

        if hit:
            r.hits += 1
            r.group_hits[tc.group] += 1
        r.mrr_sum += mrr_val
        r.latency_sum += lat
        r.stage_counts[stage] += 1
        if not results:
            r.empty += 1

        r.per_query.append(QR(
            query=tc.query, desc=tc.desc, group=tc.group,
            expected=tc.expected, found_topics=topics,
            found_scores=scores, found_stages=stages,
            hit=hit, mrr=round(mrr_val, 4), latency_ms=round(lat, 2),
        ))
    return r


def print_comparison(a: MR, b: MR, clean_stats: dict):
    print(f"\n{'='*70}")
    print(f"  KEYWORD CLEANUP IMPACT")
    print(f"{'='*70}")

    print(f"\n  Cleaning stats:")
    print(f"    Original keywords:    {clean_stats['original_total_kw']} (avg {clean_stats['original_avg_kw']}/section)")
    print(f"    Cleaned keywords:     {clean_stats['cleaned_total_kw']} (avg {clean_stats['cleaned_avg_kw']}/section)")
    print(f"    Total removed:        {clean_stats['total_removed']} ({clean_stats['reduction_pct']}%)")
    print(f"      - Cross-category:   {clean_stats['removed_cross_category']} ({clean_stats['cross_cat_keywords']} unique kw in 3+ categories)")
    print(f"      - Ultra-generic:    {clean_stats['removed_ultra_generic']} ({clean_stats['ultra_generic_keywords']} unique kw in 15+ sections)")
    print(f"      - Cap at {MAX_KW_PER_SECTION}:       {clean_stats['removed_by_cap']}")

    print(f"\n  {'Metric':<20s}  {'ORIGINAL':>15s}  {'CLEANED':>15s}  {'Delta':>10s}")
    print(f"  {'-'*20}  {'-'*15}  {'-'*15}  {'-'*10}")

    def delta(va, vb, fmt=".1%", higher_is_better=True):
        d = vb - va
        sign = "+" if d > 0 else ""
        good = (d > 0) == higher_is_better
        marker = " ✓" if good and abs(d) > 0.001 else (" ✗" if not good and abs(d) > 0.001 else "")
        if fmt == ".1%":
            return f"{sign}{d:.1%}{marker}"
        elif fmt == ".4f":
            return f"{sign}{d:.4f}{marker}"
        else:
            return f"{sign}{d:.1f}{marker}"

    print(f"  {'Hit Rate':<20s}  {a.hit_rate:>14.1%}  {b.hit_rate:>14.1%}  {delta(a.hit_rate, b.hit_rate):>10s}")
    print(f"  {'MRR':<20s}  {a.mrr:>15.4f}  {b.mrr:>15.4f}  {delta(a.mrr, b.mrr, '.4f'):>10s}")
    print(f"  {'Avg Latency ms':<20s}  {a.avg_latency:>15.1f}  {b.avg_latency:>15.1f}  {delta(a.avg_latency, b.avg_latency, '.1f', False):>10s}")
    print(f"  {'Stage exact':<20s}  {a.stage_counts.get('exact',0):>15d}  {b.stage_counts.get('exact',0):>15d}")
    print(f"  {'Stage lemma':<20s}  {a.stage_counts.get('lemma',0):>15d}  {b.stage_counts.get('lemma',0):>15d}")

    # Per-group
    print(f"\n  Per-Group Hit Rates:")
    print(f"  {'Group':<15s}  {'ORIGINAL':>12s}  {'CLEANED':>12s}  {'Delta':>8s}")
    print(f"  {'-'*15}  {'-'*12}  {'-'*12}  {'-'*8}")
    for g in sorted(set(a.group_total) | set(b.group_total)):
        at, ah = a.group_total.get(g,0), a.group_hits.get(g,0)
        bt, bh = b.group_total.get(g,0), b.group_hits.get(g,0)
        ar = ah/max(at,1)
        br = bh/max(bt,1)
        d = br - ar
        ds = f"+{d:.0%}" if d > 0 else (f"{d:.0%}" if d < 0 else "=")
        print(f"  {g:<15s}  {ah}/{at} ({ar:.0%}):>12s  {bh}/{bt} ({br:.0%}):>12s  {ds:>8s}")
    # fix formatting
    print()
    for g in sorted(set(a.group_total) | set(b.group_total)):
        at, ah = a.group_total.get(g,0), a.group_hits.get(g,0)
        bt, bh = b.group_total.get(g,0), b.group_hits.get(g,0)
        ar = ah/max(at,1); br = bh/max(bt,1)
        d = br - ar
        ds = f"+{d:.0%}" if d > 0 else (f"{d:.0%}" if d < 0 else "=")
        ap = f"{ah}/{at} ({ar:.0%})"
        bp = f"{bh}/{bt} ({br:.0%})"
        print(f"    {g:<15s}  {ap:>14s}  {bp:>14s}  {ds:>8s}")

    # Disagreements
    print(f"\n  CHANGES (queries that flipped):")
    improved = []
    degraded = []
    for qa, qb in zip(a.per_query, b.per_query):
        if qa.hit and not qb.hit:
            degraded.append((qa, qb))
        elif not qa.hit and qb.hit:
            improved.append((qa, qb))

    if improved:
        print(f"\n    IMPROVED ({len(improved)}):")
        for qa, qb in improved:
            print(f"      ✓ [{qa.desc}] {qa.query}")
            print(f"        Before: {qa.found_topics[:3]} (stage={qa.found_stages[0] if qa.found_stages else 'none'})")
            print(f"        After:  {qb.found_topics[:3]} (stage={qb.found_stages[0] if qb.found_stages else 'none'})")

    if degraded:
        print(f"\n    DEGRADED ({len(degraded)}):")
        for qa, qb in degraded:
            print(f"      ✗ [{qa.desc}] {qa.query}")
            print(f"        Before: {qa.found_topics[:3]} (stage={qa.found_stages[0] if qa.found_stages else 'none'})")
            print(f"        After:  {qb.found_topics[:3]} (stage={qb.found_stages[0] if qb.found_stages else 'none'})")

    if not improved and not degraded:
        print(f"    (no changes — all queries return same hit/miss)")

    # MRR improvements (same hit status but better/worse rank)
    mrr_improved = 0
    mrr_degraded = 0
    for qa, qb in zip(a.per_query, b.per_query):
        if qa.hit == qb.hit:
            if qb.mrr > qa.mrr + 0.01:
                mrr_improved += 1
            elif qb.mrr < qa.mrr - 0.01:
                mrr_degraded += 1

    print(f"\n    MRR shifts (same hit, different rank):")
    print(f"      Better rank after cleanup: {mrr_improved}")
    print(f"      Worse rank after cleanup:  {mrr_degraded}")

    print(f"\n  SUMMARY: {len(improved)} improved, {len(degraded)} degraded, "
          f"{len(TESTS) - len(improved) - len(degraded)} unchanged")


def main():
    print("="*70)
    print("  KEYWORD CLEANUP EXPERIMENT")
    print(f"  Strategy: remove cross-cat dupes + ultra-generic + cap at {MAX_KW_PER_SECTION}")
    print("="*70)

    print("\n[1] Loading KB...")
    kb = load_knowledge_base()
    print(f"    {len(kb.sections)} sections")

    print("[2] Cleaning keywords...")
    cleaned_kb, stats = clean_kb(kb)
    print(f"    Removed {stats['total_removed']} keywords ({stats['reduction_pct']}%)")
    print(f"    {stats['original_avg_kw']} → {stats['cleaned_avg_kw']} avg/section")

    print("[3] Building Original retriever...")
    ret_orig = CascadeRetriever(knowledge_base=kb, use_embeddings=False)

    print("[4] Building Cleaned retriever...")
    ret_clean = CascadeRetriever(knowledge_base=cleaned_kb, use_embeddings=False)

    print("[5] Running Original benchmark...")
    results_orig = run_eval(ret_orig, "ORIGINAL")

    print("[6] Running Cleaned benchmark...")
    results_clean = run_eval(ret_clean, "CLEANED")

    print_comparison(results_orig, results_clean, stats)

    # Save
    out_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "results", "benchmark_keyword_cleanup.json",
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    output = {
        "cleaning_stats": stats,
        "original": {"hit_rate": round(results_orig.hit_rate, 4), "mrr": round(results_orig.mrr, 4)},
        "cleaned": {"hit_rate": round(results_clean.hit_rate, 4), "mrr": round(results_clean.mrr, 4)},
        "improved": [],
        "degraded": [],
    }
    for qa, qb in zip(results_orig.per_query, results_clean.per_query):
        if not qa.hit and qb.hit:
            output["improved"].append({"query": qa.query, "desc": qa.desc})
        elif qa.hit and not qb.hit:
            output["degraded"].append({"query": qa.query, "desc": qa.desc})
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n  Saved: {out_path}")


if __name__ == "__main__":
    main()
