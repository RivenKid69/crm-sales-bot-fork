#!/usr/bin/env python3
"""
Benchmark: Embeddings quality on OLD vs NEW format KB sections.

Goal: Compare FRIDA embedding retrieval accuracy on:
  - NEW format sections (ПАРАМЕТРЫ blocks, disambiguation, one entity per section)
  - OLD format sections (free-form prose, inline facts)

Same FRIDA model, same pipeline, same query types — only facts format differs.
"""

import sys, os, time, json
os.environ["CUDA_VISIBLE_DEVICES"] = ""  # FRIDA → CPU

from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.settings import settings
from src.knowledge.loader import load_knowledge_base
from src.knowledge.base import KnowledgeBase
from src.knowledge.retriever import (
    CascadeRetriever, SearchResult, MatchStage, reset_retriever,
)
from src.knowledge.enhanced_retrieval import EnhancedRetrievalPipeline
from src.knowledge.category_router import CategoryRouter
from src.config_loader import ConfigLoader
from src.llm import OllamaLLM


# ─── Test cases ─────────────────────────────────────────────────────────────

@dataclass
class TestCase:
    query: str
    expected: List[str]     # substring patterns for topic names
    group: str              # "NEW" or "OLD"
    desc: str
    category_hint: str      # for readable output
    intent: str = "price_question"
    state: str = "autonomous_discovery"


# ═══════════════════════════════════════════════════════════════════════════
# GROUP A: Queries targeting NEW format sections
# (pricing.yaml, equipment.yaml — structured ПАРАМЕТРЫ, ⚠️ НЕ ПУТАТЬ)
# ═══════════════════════════════════════════════════════════════════════════

NEW_FORMAT_TESTS = [
    # --- Pricing: тарифы (NEW format — structured ПАРАМЕТРЫ) ---
    TestCase("сколько стоит тариф Mini?", ["tariff_mini", "wipon_mini", "pricing_mini"], "NEW", "Тариф Mini цена", "pricing"),
    TestCase("тариф Lite, цена в год", ["tariff_lite", "pricing_lite"], "NEW", "Тариф Lite цена", "pricing"),
    TestCase("тариф Standard на 3 точки", ["tariff_standard", "pricing_standard", "pricing_two_locations", "lite_vs_standard"], "NEW", "Тариф Standard", "pricing"),
    TestCase("тариф Pro, сколько в год?", ["tariff_pro", "pricing_pro"], "NEW", "Тариф Pro цена", "pricing"),
    TestCase("какие тарифы у вас есть?", ["tariff_overview", "choose_tariff", "tariffs"], "NEW", "Обзор тарифов", "pricing"),
    TestCase("пробный период бесплатно?", ["pricing_trial", "trial"], "NEW", "Пробный период", "pricing"),
    TestCase("рассрочка на оборудование есть?", ["installment", "pricing_payment"], "NEW", "Рассрочка", "pricing"),
    TestCase("УКМ Wipon Pro цена", ["wipon_pro_pricing", "pricing_wipon_pro", "pricing_ukm"], "NEW", "УКМ Wipon Pro", "pricing"),
    TestCase("цена за сеть магазинов", ["pricing_multistore", "pricing_network", "pricing_tis", "pricing_5_point"], "NEW", "Мультиточка прайс", "pricing"),
    TestCase("Wipon Cashback стоимость подписки", ["cashback", "wipon_cashback"], "NEW", "Cashback прайс", "pricing"),

    # --- Pricing: ТИС формула (NEW format — готовые расчёты) ---
    TestCase("ТИС цена за 7 точек", ["tis_pricing", "pricing_tis"], "NEW", "ТИС формула 7 точек", "pricing"),
    TestCase("сколько стоит дополнительная точка ТИС?", ["additional_point_tis", "tis_second_point", "tis_pricing", "additional_point"], "NEW", "Доп. точка ТИС", "pricing"),

    # --- Equipment: моноблоки (NEW format — ПАРАМЕТРЫ) ---
    TestCase("POS моноблок i3 характеристики", ["pos_i3", "pricing_monoblocks"], "NEW", "POS i3 specs", "equipment"),
    TestCase("POS DUO с двумя экранами цена", ["pos_duo", "pricing_monoblocks"], "NEW", "POS DUO", "equipment"),
    TestCase("все моноблоки, покажите линейку", ["pricing_monoblocks", "monoblock"], "NEW", "Обзор моноблоков", "equipment"),
    TestCase("Wipon 5 в 1 сколько стоит?", ["5in1", "pricing_monoblocks", "wipon_5"], "NEW", "5 в 1 цена", "equipment"),

    # --- Equipment: сканеры (NEW format — ПАРАМЕТРЫ) ---
    TestCase("Pocket Scanner цена", ["pocket_scanner", "pricing_pocket"], "NEW", "Pocket Scanner", "equipment"),
    TestCase("Smart Scanner чем отличается от Pocket?", ["smart_scanner", "pocket_scanner"], "NEW", "Smart vs Pocket", "equipment"),
    TestCase("какие сканеры штрихкодов продаёте?", ["scanner", "pricing_scanners"], "NEW", "Обзор сканеров", "equipment"),

    # --- Equipment: принтеры (NEW format — ПАРАМЕТРЫ) ---
    TestCase("принтер этикеток XP420B цена", ["xp420b", "label_printer", "pricing_printers"], "NEW", "XP420B цена", "equipment"),
    TestCase("принтер чеков GP-C58", ["gp_c58", "xprinter_58", "pricing_printers"], "NEW", "GP-C58", "equipment"),

    # --- Equipment: комплекты (NEW format — ⚠️ НЕ ПУТАТЬ) ---
    TestCase("комплект оборудования Standard что входит?", ["kit_standard", "standard_kit", "ready_kits"], "NEW", "Комплект Standard", "equipment"),
    TestCase("комплект PRO что в составе?", ["kit_pro", "pro_kit"], "NEW", "Комплект PRO", "equipment"),

    # --- Promotions (NEW format) ---
    TestCase("есть ли сейчас акции?", ["promotions_", "promotion", "discount", "акци"], "NEW", "Акции", "promotions", "question_features"),
]

# ═══════════════════════════════════════════════════════════════════════════
# GROUP B: Queries targeting OLD format sections
# (products.yaml, features.yaml, tis.yaml, support.yaml, etc.)
# ═══════════════════════════════════════════════════════════════════════════

OLD_FORMAT_TESTS = [
    # --- Products (OLD format — inline prose) ---
    TestCase("что такое Wipon Kassa?", ["wipon_kassa"], "OLD", "Wipon Kassa описание", "products", "question_features"),
    TestCase("расскажите про Wipon Desktop", ["wipon_desktop", "desktop"], "OLD", "Desktop описание", "products", "question_features"),
    TestCase("Wipon ТИС для упрощёнки", ["wipon_tis", "tis_wipon", "tis_decode", "tis_what"], "OLD", "Wipon ТИС описание", "products", "question_features"),
    TestCase("модуль Cashback как работает?", ["wipon_cashback", "cashback", "bonus_system", "loyalty"], "OLD", "Cashback описание", "products", "question_features"),
    TestCase("мобильное приложение Wipon", ["mobile_app", "mobile_"], "OLD", "Мобильное приложение", "products", "question_features"),
    TestCase("проверка алкоголя УКМ", ["wipon_pro", "alcohol", "ukm"], "OLD", "Wipon Pro УКМ", "products", "question_features"),

    # --- Features (OLD format — inline prose) ---
    TestCase("складской учёт как устроен?", ["inventory"], "OLD", "Склад", "features", "question_features"),
    TestCase("какие отчёты можно строить?", ["reports", "analytics", "excel"], "OLD", "Отчёты", "features", "question_features"),
    TestCase("кадровый учёт сотрудников", ["employees", "salary", "hr"], "OLD", "Сотрудники", "features", "question_features"),

    # --- TIS (OLD format — short inline facts) ---
    TestCase("как работает ТИС?", ["tis_how_works", "tis_consultation", "tis_abbreviation", "tis_decode"], "OLD", "ТИС принцип работы", "tis", "question_features"),
    TestCase("чем ТИС лучше обычной кассы?", ["tis_vs_regular"], "OLD", "ТИС vs касса", "tis", "question_features"),
    TestCase("ТИС при маленьком обороте стоит?", ["tis_small_turnover", "tis_small"], "OLD", "ТИС малые обороты", "tis", "question_features"),
    TestCase("только открыл ИП, нужен ли ТИС?", ["tis_new_ip", "ip_registration", "ip_connect"], "OLD", "ТИС для нового ИП", "tis", "question_features"),
    TestCase("ТИС для ТОО подходит?", ["tis_too", "open_too"], "OLD", "ТИС для ТОО", "tis", "question_features"),

    # --- Support (OLD format) ---
    TestCase("как обучить сотрудников работе?", ["support_training", "training", "onboarding"], "OLD", "Обучение", "support", "question_features"),
    TestCase("техподдержка 24/7 есть?", ["support_sla", "support_channel", "support_weekend", "support_hours"], "OLD", "SLA поддержки", "support", "question_features"),
    TestCase("как быстро внедряется система?", ["support_implement", "support_registration_time", "support_start", "connection_speed"], "OLD", "Скорость внедрения", "support", "question_features"),

    # --- Stability (OLD format) ---
    TestCase("что будет если пропадёт интернет?", ["stability_offline", "stability_no_internet", "stability_internet", "stability_weak"], "OLD", "Без интернета", "stability", "question_features"),
    TestCase("данные в безопасности?", ["stability_backup", "stability_data", "data_protection", "security_data"], "OLD", "Безопасность данных", "stability", "question_features"),

    # --- Integrations (OLD format) ---
    TestCase("интеграция с 1С есть?", ["1c", "integrations_1c"], "OLD", "1С интеграция", "integrations", "question_integrations"),
    TestCase("работаете ли с Kaspi?", ["kaspi", "integrations_kaspi"], "OLD", "Kaspi интеграция", "integrations", "question_integrations"),
    TestCase("можно подключить маркетплейсы?", ["marketplace", "integrations_marketplace"], "OLD", "Маркетплейсы", "integrations", "question_integrations"),

    # --- Competitors (OLD format) ---
    TestCase("чем лучше iiko?", ["vs_others", "competitors_", "iiko"], "OLD", "vs iiko", "competitors", "comparison"),
    TestCase("чем отличаетесь от umag?", ["competitors_umag", "umag"], "OLD", "vs umag", "competitors", "comparison"),

    # --- Regions (OLD format) ---
    TestCase("работаете в Караганде?", ["regions_", "karaganda"], "OLD", "Караганда", "regions", "question_features"),
]

ALL_TESTS = NEW_FORMAT_TESTS + OLD_FORMAT_TESTS


# ─── Custom retriever ────────────────────────────────────────────────────────

class EmbeddingsOnlyRetriever(CascadeRetriever):
    """Stage 3 only: skip keywords, use FRIDA semantic search."""
    def __init__(self, kb, threshold=0.3):
        super().__init__(knowledge_base=kb, use_embeddings=True, semantic_threshold=threshold)

    def search(self, query, category=None, categories=None, top_k=3):
        if not query or not query.strip():
            return []
        sections = self.kb.sections
        if categories:
            sections = [s for s in sections if s.category in categories]
        elif category:
            sections = [s for s in sections if s.category == category]
        if not sections:
            return []
        return self._semantic_search(query, sections, top_k)


# ─── Metrics ─────────────────────────────────────────────────────────────────

@dataclass
class QueryResult:
    query: str
    desc: str
    group: str
    category_hint: str
    expected: List[str]
    fact_keys: List[str]
    hit: bool
    mrr: float
    latency_ms: float
    top1_score: float
    facts_snippet: str


@dataclass
class GroupResults:
    total: int = 0
    hits: int = 0
    mrr_sum: float = 0.0
    latency_sum: float = 0.0
    per_query: List[QueryResult] = field(default_factory=list)
    per_cat: Dict[str, List[bool]] = field(default_factory=lambda: defaultdict(list))

    @property
    def hit_rate(self): return self.hits / max(self.total, 1)
    @property
    def mrr(self): return self.mrr_sum / max(self.total, 1)
    @property
    def avg_latency(self): return self.latency_sum / max(self.total, 1)


def matches_pattern(key: str, patterns: List[str]) -> bool:
    key_l = key.lower()
    return any(p.lower() in key_l for p in patterns)


# ─── Pipeline runner ─────────────────────────────────────────────────────────

def run_tests(
    pipeline: EnhancedRetrievalPipeline,
    retriever: CascadeRetriever,
    tests: List[TestCase],
    flow_config,
    kb: KnowledgeBase,
) -> Dict[str, GroupResults]:
    """Run all tests, split results by group (NEW/OLD)."""
    results = {"NEW": GroupResults(), "OLD": GroupResults()}

    for tc in tests:
        gr = results[tc.group]
        gr.total += 1

        t0 = time.perf_counter()
        with patch("src.knowledge.enhanced_retrieval.get_retriever", return_value=retriever):
            facts_text, urls, fact_keys = pipeline.retrieve(
                user_message=tc.query,
                intent=tc.intent,
                state=tc.state,
                flow_config=flow_config,
                kb=kb,
                recently_used_keys=set(),
                history=[],
                secondary_intents=[],
            )
        latency = (time.perf_counter() - t0) * 1000

        # Evaluate
        hit = False
        mrr_val = 0.0
        for rank, key in enumerate(fact_keys, 1):
            if matches_pattern(key, tc.expected):
                if not hit:
                    mrr_val = 1.0 / rank
                hit = True
                break

        if hit:
            gr.hits += 1
        gr.mrr_sum += mrr_val
        gr.latency_sum += latency
        gr.per_cat[tc.category_hint].append(hit)

        # Try to get top-1 cosine score from retriever internals (not exposed, use 0)
        top1_score = 0.0

        gr.per_query.append(QueryResult(
            query=tc.query, desc=tc.desc, group=tc.group,
            category_hint=tc.category_hint, expected=tc.expected,
            fact_keys=fact_keys, hit=hit, mrr=mrr_val,
            latency_ms=latency, top1_score=top1_score,
            facts_snippet=facts_text[:150] if facts_text else "",
        ))

        status = "✅" if hit else "❌"
        print(f"  {status} [{tc.group:3s}|{tc.category_hint:12s}] {tc.desc}: keys={fact_keys[:3]}")

    return results


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 80)
    print("BENCHMARK: Embeddings on OLD format vs NEW format KB sections")
    print("=" * 80)

    # 1. Load KB
    print("\n📦 Loading KB...")
    kb = load_knowledge_base()
    print(f"   Loaded {len(kb.sections)} sections")

    # Count new vs old format
    new_fmt = sum(1 for s in kb.sections if "ПАРАМЕТРЫ:" in s.facts)
    disambig = sum(1 for s in kb.sections if "НЕ ПУТАТЬ" in s.facts)
    print(f"   Sections with ПАРАМЕТРЫ: {new_fmt}")
    print(f"   Sections with НЕ ПУТАТЬ: {disambig}")
    print(f"   Old format (no ПАРАМЕТРЫ): {len(kb.sections) - new_fmt}")

    # 2. Analyze facts length by format
    new_lengths = [len(s.facts) for s in kb.sections if "ПАРАМЕТРЫ:" in s.facts]
    old_lengths = [len(s.facts) for s in kb.sections if "ПАРАМЕТРЫ:" not in s.facts]
    if new_lengths:
        print(f"\n   Facts length (NEW format): avg={sum(new_lengths)/len(new_lengths):.0f} chars, "
              f"min={min(new_lengths)}, max={max(new_lengths)}")
    if old_lengths:
        print(f"   Facts length (OLD format): avg={sum(old_lengths)/len(old_lengths):.0f} chars, "
              f"min={min(old_lengths)}, max={max(old_lengths)}")

    # 3. Build embeddings retriever (FRIDA on CPU)
    print("\n🧠 Building FRIDA embeddings (CPU)...")
    t0 = time.perf_counter()
    emb_retriever = EmbeddingsOnlyRetriever(kb, threshold=0.3)
    emb_time = time.perf_counter() - t0
    print(f"   FRIDA indexed {len(kb.sections)} sections in {emb_time:.1f}s")

    # 4. Setup pipeline
    print("\n🔧 Setting up EnhancedRetrievalPipeline...")
    loader = ConfigLoader()
    _config, flow_config = loader.load_bundle(config_name="default", flow_name="autonomous")
    print(f"   Flow: {flow_config.name}")
    llm = OllamaLLM()
    cat_router = CategoryRouter(llm, top_k=3)
    pipeline = EnhancedRetrievalPipeline(llm=llm, category_router=cat_router)

    # 5. Run benchmark
    print("\n" + "=" * 80)
    print("RUNNING: All tests through FRIDA embeddings + EnhancedRetrievalPipeline")
    print("=" * 80)
    results = run_tests(pipeline, emb_retriever, ALL_TESTS, flow_config, kb)

    # 6. Report
    print("\n" + "=" * 80)
    print("RESULTS: Embeddings on NEW format vs OLD format")
    print("=" * 80)

    for label in ["NEW", "OLD"]:
        gr = results[label]
        print(f"\n{'─' * 50}")
        format_desc = "ПАРАМЕТРЫ + НЕ ПУТАТЬ" if label == "NEW" else "Inline prose"
        print(f"  {label} format ({format_desc})")
        print(f"{'─' * 50}")
        print(f"  Hit rate:     {gr.hit_rate:.1%} ({gr.hits}/{gr.total})")
        print(f"  MRR:          {gr.mrr:.4f}")
        print(f"  Avg latency:  {gr.avg_latency:.0f}ms")

        print(f"\n  Per category:")
        for cat in sorted(gr.per_cat.keys()):
            hits_list = gr.per_cat[cat]
            h = sum(hits_list)
            t = len(hits_list)
            print(f"    {cat:15s}: {h}/{t} = {h/t:.0%}")

    # 7. Missed queries deep dive
    for label in ["NEW", "OLD"]:
        gr = results[label]
        misses = [q for q in gr.per_query if not q.hit]
        if misses:
            print(f"\n{'─' * 50}")
            print(f"  MISSES ({label} format): {len(misses)} queries")
            print(f"{'─' * 50}")
            for q in misses:
                print(f"  ❌ {q.desc}")
                print(f"     Query: {q.query}")
                print(f"     Expected: {q.expected}")
                print(f"     Got: {q.fact_keys[:5]}")
                print()

    # 8. Summary comparison
    new_r = results["NEW"]
    old_r = results["OLD"]
    delta_hit = new_r.hit_rate - old_r.hit_rate
    delta_mrr = new_r.mrr - old_r.mrr

    print(f"\n{'=' * 80}")
    print("COMPARISON SUMMARY")
    print(f"{'=' * 80}")
    print(f"  NEW format hit rate: {new_r.hit_rate:.1%}")
    print(f"  OLD format hit rate: {old_r.hit_rate:.1%}")
    print(f"  Delta:               {delta_hit:+.1%}")
    print()
    print(f"  NEW format MRR:      {new_r.mrr:.4f}")
    print(f"  OLD format MRR:      {old_r.mrr:.4f}")
    print(f"  Delta:               {delta_mrr:+.4f}")
    print()

    if delta_hit > 0.05:
        verdict = "NEW format ЗНАЧИТЕЛЬНО лучше для эмбеддингов"
    elif delta_hit > 0:
        verdict = "NEW format НЕМНОГО лучше для эмбеддингов"
    elif delta_hit > -0.05:
        verdict = "Разница МИНИМАЛЬНАЯ — формат не влияет на эмбеддинги существенно"
    else:
        verdict = "OLD format лучше (NEW format хуже для эмбеддингов)"

    print(f"  VERDICT: {verdict}")

    # 9. Save
    output = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "kb_sections": len(kb.sections),
        "new_format_sections": new_fmt,
        "disambig_sections": disambig,
        "tests": {"NEW": len(NEW_FORMAT_TESTS), "OLD": len(OLD_FORMAT_TESTS)},
        "facts_length": {
            "new_avg": sum(new_lengths) / max(len(new_lengths), 1),
            "old_avg": sum(old_lengths) / max(len(old_lengths), 1),
        },
        "results": {
            label: {
                "hit_rate": results[label].hit_rate,
                "mrr": results[label].mrr,
                "avg_latency_ms": results[label].avg_latency,
                "per_category": {
                    cat: {"hits": sum(h), "total": len(h)}
                    for cat, h in results[label].per_cat.items()
                },
                "misses": [
                    {"desc": q.desc, "query": q.query, "expected": q.expected, "got": q.fact_keys[:5]}
                    for q in results[label].per_query if not q.hit
                ],
            }
            for label in ["NEW", "OLD"]
        },
        "verdict": verdict,
    }

    outpath = "results/benchmark_new_format.json"
    os.makedirs("results", exist_ok=True)
    with open(outpath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Results saved to {outpath}")


if __name__ == "__main__":
    main()
