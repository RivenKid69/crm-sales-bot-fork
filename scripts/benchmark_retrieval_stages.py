#!/usr/bin/env python3
"""
Benchmark: Keywords (Stage 1+2) vs Embeddings (Stage 3)
through the real EnhancedRetrievalPipeline.

Both modes use the SAME:
  - LLM (Ministral via Ollama) for CategoryRouter + query rewriting
  - EnhancedRetrievalPipeline orchestration (rewrite → route → decompose → RRF → backfill)
  - flow_config, state, KB

Only difference: underlying CascadeRetriever search method.
  Mode A: Stage 1 (exact) + Stage 2 (lemma)     — current production
  Mode B: Stage 3 (semantic/FRIDA embeddings)    — alternative

FRIDA runs on CPU to avoid GPU OOM with Ollama.
"""

import sys, os, time, json
os.environ["CUDA_VISIBLE_DEVICES"] = ""  # FRIDA → CPU

from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple, Set, Any
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


# ─── Test cases ───────────────────────────────────────────────────────────────
# (query, expected_topic_patterns, group, description)
# expected = substring patterns; hit = at least 1 fact_key matches any pattern.

@dataclass
class TestCase:
    query: str
    expected: List[str]   # substring patterns for fact_keys
    group: str
    desc: str
    intent: str = "price_question"  # default; overridden per group
    state: str = "autonomous_discovery"


TESTS: List[TestCase] = [
    # ── PRICING ──
    TestCase("Сколько стоит ваша система?", ["tariffs", "pricing_tariff"], "Pricing", "Прямой вопрос о цене", "price_question"),
    TestCase("Какие тарифы у вас есть?", ["tariffs", "pricing_tariff"], "Pricing", "Тарифы", "price_question"),
    TestCase("цена за 5 точек", ["pricing_multistore", "pricing_5", "tariffs"], "Pricing", "Цена за 5 точек", "price_question"),
    TestCase("стоимость на 10 касс", ["tariffs", "pricing_tariff", "pricing_multistore"], "Pricing", "Стоимость 10 касс", "price_question"),
    TestCase("есть ли бесплатная версия?", ["free", "pricing_free", "pricing_trial"], "Pricing", "Бесплатная версия", "price_question"),
    TestCase("рассрочка есть?", ["pricing_installment", "pricing_payment"], "Pricing", "Рассрочка", "price_question"),
    TestCase("почём самый дешёвый тариф?", ["tariffs", "pricing_tariff_mini", "products_wipon_mini"], "Pricing", "Дешёвый тариф", "price_question"),

    # ── FEATURES ──
    TestCase("какие отчёты можно строить?", ["analytics_", "reports"], "Features", "Отчёты", "question_features"),
    TestCase("как работает учёт товаров?", ["inventory_"], "Features", "Учёт товаров", "question_features"),
    TestCase("можно ли управлять сотрудниками?", ["employees_"], "Features", "Управление сотрудниками", "question_features"),
    TestCase("есть ли мобильное приложение?", ["mobile_app", "mobile_"], "Features", "Мобильное приложение", "question_features"),
    TestCase("какие функции у кассы?", ["features_cashier", "features_pos", "wipon_kassa"], "Features", "Функции кассы", "question_features"),
    TestCase("как настроить систему лояльности?", ["promotions_loyalty", "promotions_bonus", "promotions_discount"], "Features", "Лояльность", "question_features"),
    TestCase("работает ли с маркировкой товаров?", ["integrations_marking", "marking"], "Features", "Маркировка", "question_features"),

    # ── INTEGRATIONS ──
    TestCase("интеграция с 1С есть?", ["1c", "integrations_1c"], "Integrations", "1С", "question_integrations"),
    TestCase("работает ли с Kaspi?", ["kaspi"], "Integrations", "Kaspi", "question_integrations"),
    TestCase("можно ли подключить эквайринг?", ["integrations_bank", "tis_pos_terminal", "payment", "acquiring"], "Integrations", "Эквайринг", "question_integrations"),
    TestCase("есть ли интеграция с маркетплейсами?", ["marketplace", "wildberries"], "Integrations", "Маркетплейсы", "question_integrations"),

    # ── SUPPORT ──
    TestCase("как обучить сотрудников работе с системой?", ["support_training", "support_onboarding"], "Support", "Обучение", "question_features"),
    TestCase("есть ли техническая поддержка 24/7?", ["support_sla", "support_channel", "help"], "Support", "Поддержка 24/7", "question_features"),
    TestCase("как быстро внедряется система?", ["support_implement", "support_onboarding", "tis_connection_speed"], "Support", "Внедрение", "question_features"),
    TestCase("что делать если система сломалась?", ["support_broken", "stability_"], "Support", "Сломалась", "question_features"),

    # ── EQUIPMENT ──
    TestCase("какое оборудование нужно?", ["equipment_"], "Equipment", "Оборудование", "question_features"),
    TestCase("подходит ли обычный принтер чеков?", ["equipment_", "printer"], "Equipment", "Принтер чеков", "question_features"),
    TestCase("нужен ли сканер штрих-кодов?", ["equipment_", "scanner", "barcode"], "Equipment", "Сканер", "question_features"),

    # ── FISCAL ──
    TestCase("как работает фискализация?", ["fiscal_"], "Fiscal", "Фискализация", "question_features"),
    TestCase("нужен ли ККМ?", ["fiscal_", "tis_"], "Fiscal", "ККМ", "question_features"),
    TestCase("как отправлять чеки в ОФД?", ["fiscal_ofd", "fiscal_receipt", "fiscal_send"], "Fiscal", "ОФД", "question_features"),

    # ── COMPETITORS ──
    TestCase("чем вы лучше iiko?", ["vs_others", "competitors_", "iiko"], "Competitors", "iiko", "comparison"),
    TestCase("чем отличается от umag?", ["competitors_umag", "umag"], "Competitors", "umag", "comparison"),
    TestCase("почему стоит выбрать wipon?", ["competitors_general", "vs_others", "why_wipon"], "Competitors", "Почему Wipon", "comparison"),

    # ── PRODUCTS ──
    TestCase("какие продукты у вас есть?", ["products_wipon", "overview", "products_what"], "Products", "Продукты", "question_features"),
    TestCase("что такое Wipon Desktop?", ["wipon_desktop", "products_desktop"], "Products", "Desktop", "question_features"),
    TestCase("расскажите про Wipon Kassa", ["wipon_kassa", "products_kassa"], "Products", "Kassa", "question_features"),

    # ── REGIONS ──
    TestCase("работаете ли вы в Алматы?", ["regions_", "coverage"], "Regions", "Алматы", "question_features"),
    TestCase("доставляете ли в регионы?", ["regions_delivery"], "Regions", "Доставка", "question_features"),

    # ── TIS ──
    TestCase("что такое ТИС?", ["tis_"], "TIS", "Что такое ТИС", "question_features"),
    TestCase("какой налоговый режим мне выбрать?", ["tis_retail", "tis_earning", "tis_too"], "TIS", "Налоговый режим", "question_features"),
    TestCase("нужно ли мне СНТ?", ["snt", "fiscal_document"], "TIS", "СНТ", "question_features"),
    TestCase("как подключить ЭСФ?", ["esf", "fiscal_document"], "TIS", "ЭСФ", "question_features"),

    # ── STABILITY ──
    TestCase("что будет если интернет пропадёт?", ["stability_offline", "stability_no_internet", "stability_internet"], "Stability", "Без интернета", "question_features"),
    TestCase("насколько надёжна ваша система?", ["stability_"], "Stability", "Надёжность", "question_features"),

    # ── TRICKY ──
    TestCase("мне нужна автоматизация магазина", ["products_wipon", "overview"], "Tricky", "Автоматизация", "question_features"),
    TestCase("а если у меня сеть магазинов?", ["faq_network", "pricing_multistore", "multistore"], "Tricky", "Сеть магазинов", "question_features"),
    TestCase("не стоит тратить время", [], "Tricky", "Отказ (не стоит ≠ цена)", "rejection"),
    TestCase("у нас 5 точек по Казахстану", ["regions_", "coverage", "pricing_multistore"], "Tricky", "5 точек", "situation_provided"),
    TestCase("қандай бағалар бар?", ["tariffs", "pricing_tariff", "pricing_"], "Tricky", "KZ: какие цены", "price_question"),
    TestCase("жүйе қанша тұрады?", ["tariffs", "pricing_"], "Tricky", "KZ: сколько стоит", "price_question"),
    TestCase("Мне нужно учёт товаров вести", ["inventory_"], "Tricky", "Мне нужно (не no_need)", "question_features"),
    TestCase("какая СУБД используется?", ["support_db", "stability_data"], "Tricky", "СУБД", "question_features"),
    TestCase("можно ли платить через Kaspi QR?", ["kaspi"], "Tricky", "Kaspi QR", "question_features"),
    TestCase("ваша система работает на планшете?", ["mobile_tablet", "mobile_app", "mobile_kassa"], "Tricky", "Планшет", "question_features"),
    TestCase("как вести инвентаризацию?", ["inventory_revision", "inventory_stocktaking"], "Tricky", "Инвентаризация", "question_features"),
    TestCase("можно ли импортировать товары из Excel?", ["inventory_import", "features_import", "excel"], "Tricky", "Импорт Excel", "question_features"),
]


# ─── Metrics ──────────────────────────────────────────────────────────────────

@dataclass
class QueryResult:
    query: str
    desc: str
    group: str
    expected: List[str]
    fact_keys: List[str]
    hit: bool
    mrr: float
    latency_ms: float
    facts_len: int
    categories_routed: Optional[List[str]] = None


@dataclass
class ModeResults:
    mode: str
    total: int = 0
    hits: int = 0
    mrr_sum: float = 0.0
    latency_sum: float = 0.0
    empty_facts: int = 0
    per_query: List[QueryResult] = field(default_factory=list)
    group_hits: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    group_total: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    @property
    def hit_rate(self): return self.hits / max(self.total, 1)
    @property
    def mrr(self): return self.mrr_sum / max(self.total, 1)
    @property
    def avg_latency(self): return self.latency_sum / max(self.total, 1)


def matches_pattern(key: str, patterns: List[str]) -> bool:
    key_l = key.lower()
    return any(p.lower() in key_l for p in patterns)


# ─── Custom retrievers ───────────────────────────────────────────────────────

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
        # Skip Stage 1+2, go directly to semantic
        return self._semantic_search(query, sections, top_k)


# ─── Pipeline runner ─────────────────────────────────────────────────────────

def run_pipeline(
    pipeline: EnhancedRetrievalPipeline,
    retriever_instance: CascadeRetriever,
    tests: List[TestCase],
    mode_name: str,
    flow_config,
    kb: KnowledgeBase,
) -> ModeResults:
    """Run all tests through EnhancedRetrievalPipeline, patching get_retriever."""
    results = ModeResults(mode=mode_name)

    for tc in tests:
        results.total += 1
        results.group_total[tc.group] += 1

        # Patch get_retriever to return our specific retriever
        t0 = time.perf_counter()
        with patch("src.knowledge.enhanced_retrieval.get_retriever", return_value=retriever_instance):
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
        if not tc.expected:
            # Negative test (rejection) — always count as hit
            hit = True
            mrr_val = 1.0
        else:
            hit = False
            mrr_val = 0.0
            for rank, key in enumerate(fact_keys, 1):
                if matches_pattern(key, tc.expected):
                    if not hit:
                        mrr_val = 1.0 / rank
                    hit = True
                    break

        if hit:
            results.hits += 1
            results.group_hits[tc.group] += 1
        results.mrr_sum += mrr_val
        results.latency_sum += latency

        if not facts_text.strip():
            results.empty_facts += 1

        results.per_query.append(QueryResult(
            query=tc.query, desc=tc.desc, group=tc.group,
            expected=tc.expected, fact_keys=fact_keys,
            hit=hit, mrr=round(mrr_val, 4),
            latency_ms=round(latency, 1),
            facts_len=len(facts_text),
        ))

    return results


# ─── Output ──────────────────────────────────────────────────────────────────

def print_mode(r: ModeResults):
    print(f"\n{'='*70}")
    print(f"  MODE: {r.mode}")
    print(f"{'='*70}")
    print(f"  Hit Rate:      {r.hits}/{r.total} = {r.hit_rate:.1%}")
    print(f"  MRR:           {r.mrr:.4f}")
    print(f"  Avg Latency:   {r.avg_latency:.0f} ms")
    print(f"  Empty Facts:   {r.empty_facts}/{r.total}")

    print(f"\n  Per-Group:")
    for g in sorted(r.group_total.keys()):
        t = r.group_total[g]
        h = r.group_hits.get(g, 0)
        pct = h / max(t, 1)
        bar = "█" * int(pct * 20) + "░" * (20 - int(pct * 20))
        print(f"    {g:15s}  {bar}  {h}/{t} ({pct:.0%})")

    misses = [q for q in r.per_query if not q.hit]
    if misses:
        print(f"\n  MISSES ({len(misses)}):")
        for m in misses:
            keys_str = ", ".join(m.fact_keys[:4]) if m.fact_keys else "(none)"
            exp_str = ", ".join(m.expected[:3])
            print(f"    ✗ [{m.desc}] Q: {m.query}")
            print(f"      Expected: {exp_str}")
            print(f"      Got keys: {keys_str}")


def print_comparison(a: ModeResults, b: ModeResults):
    print(f"\n{'='*70}")
    print(f"  HEAD-TO-HEAD: {a.mode} vs {b.mode}")
    print(f"{'='*70}")

    print(f"  {'Metric':<20s}  {a.mode:>20s}  {b.mode:>20s}")
    print(f"  {'-'*20}  {'-'*20}  {'-'*20}")
    print(f"  {'Hit Rate':<20s}  {a.hit_rate:>19.1%}  {b.hit_rate:>19.1%}")
    print(f"  {'MRR':<20s}  {a.mrr:>20.4f}  {b.mrr:>20.4f}")
    print(f"  {'Avg Latency ms':<20s}  {a.avg_latency:>20.0f}  {b.avg_latency:>20.0f}")
    print(f"  {'Empty Facts':<20s}  {a.empty_facts:>20d}  {b.empty_facts:>20d}")

    print(f"\n  Per-Group:")
    print(f"  {'Group':<15s}  {a.mode:>20s}  {b.mode:>20s}  {'Winner':>10s}")
    print(f"  {'-'*15}  {'-'*20}  {'-'*20}  {'-'*10}")
    all_groups = sorted(set(a.group_total) | set(b.group_total))
    for g in all_groups:
        at, ah = a.group_total.get(g, 0), a.group_hits.get(g, 0)
        bt, bh = b.group_total.get(g, 0), b.group_hits.get(g, 0)
        ap = f"{ah}/{at} ({ah/max(at,1):.0%})"
        bp = f"{bh}/{bt} ({bh/max(bt,1):.0%})"
        winner = "A" if ah > bh else ("B" if bh > ah else "=")
        print(f"  {g:<15s}  {ap:>20s}  {bp:>20s}  {winner:>10s}")

    # Disagreements
    print(f"\n  DISAGREEMENTS:")
    n_disagree = 0
    a_wins = 0
    b_wins = 0
    for qa, qb in zip(a.per_query, b.per_query):
        if qa.hit != qb.hit:
            n_disagree += 1
            winner = a.mode if qa.hit else b.mode
            if qa.hit: a_wins += 1
            else: b_wins += 1
            print(f"    [{qa.desc}] Winner: {winner}")
            print(f"      Q: {qa.query}")
            print(f"      {a.mode}: {'HIT' if qa.hit else 'MISS'} keys={qa.fact_keys[:3]}")
            print(f"      {b.mode}: {'HIT' if qb.hit else 'MISS'} keys={qb.fact_keys[:3]}")

    print(f"\n  Total disagreements: {n_disagree}/{len(a.per_query)}")
    print(f"  {a.mode} wins: {a_wins},  {b.mode} wins: {b_wins}")


def save_json(a: ModeResults, b: ModeResults, path: str):
    def mode_dict(r):
        return {
            "hit_rate": round(r.hit_rate, 4), "mrr": round(r.mrr, 4),
            "avg_latency_ms": round(r.avg_latency, 1),
            "empty_facts": r.empty_facts,
            "group_stats": {
                g: {"hits": r.group_hits.get(g, 0), "total": r.group_total[g]}
                for g in r.group_total
            },
            "per_query": [
                {"query": q.query, "desc": q.desc, "group": q.group,
                 "expected": q.expected, "fact_keys": q.fact_keys,
                 "hit": q.hit, "mrr": q.mrr, "latency_ms": q.latency_ms,
                 "facts_len": q.facts_len}
                for q in r.per_query
            ],
        }
    out = {a.mode: mode_dict(a), b.mode: mode_dict(b)}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n  Saved: {path}")


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    print("="*70)
    print("  RETRIEVAL BENCHMARK: Keywords vs Embeddings")
    print("  Through real EnhancedRetrievalPipeline + Ollama LLM")
    print("="*70)

    # 1. Load KB
    print("\n[1] Loading KB...")
    kb = load_knowledge_base()
    print(f"    {len(kb.sections)} sections")

    # 2. Load flow config
    print("[2] Loading flow config (autonomous)...")
    loader = ConfigLoader()
    _config, flow_config = loader.load_bundle(config_name="default", flow_name="autonomous")
    print(f"    Flow: {flow_config.name}")

    # 3. Init LLM + CategoryRouter
    print("[3] Connecting to Ollama LLM...")
    llm = OllamaLLM()
    router = CategoryRouter(llm, top_k=3)
    print(f"    Model: {settings.llm.model}")

    # 4. Init retrievers
    print("[4] Building Keywords-Only retriever (Stage 1+2)...")
    ret_kw = CascadeRetriever(knowledge_base=kb, use_embeddings=False)

    print("[5] Building Embeddings-Only retriever (FRIDA on CPU, threshold=0.3)...")
    ret_emb = EmbeddingsOnlyRetriever(kb, threshold=0.3)
    print(f"    Indexed {len(kb.sections)} sections with FRIDA embeddings")

    # 5. Create pipeline (shared for both modes — same LLM, router)
    pipeline = EnhancedRetrievalPipeline(llm=llm, category_router=router)

    # 6. Run Mode A: Keywords
    print("\n[6] Running Mode A: keywords_only (through EnhancedRetrievalPipeline)...")
    results_kw = run_pipeline(pipeline, ret_kw, TESTS, "keywords_only", flow_config, kb)
    print_mode(results_kw)

    # 7. Run Mode B: Embeddings
    print("\n[7] Running Mode B: embeddings_only (through EnhancedRetrievalPipeline)...")
    results_emb = run_pipeline(pipeline, ret_emb, TESTS, "embeddings_only", flow_config, kb)
    print_mode(results_emb)

    # 8. Comparison
    print_comparison(results_kw, results_emb)

    # 9. Save
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "results", "benchmark_retrieval_stages.json")
    save_json(results_kw, results_emb, out)


if __name__ == "__main__":
    main()
