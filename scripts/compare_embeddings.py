#!/usr/bin/env python3
"""
Сравнение FRIDA vs Qwen3-Embedding-4B на реальных запросах по KB.

Метрики:
- Top-1/3/5 Hit Rate: нашёл ли правильную секцию в top-K
- MRR (Mean Reciprocal Rank): средняя позиция правильного ответа
- Cosine similarity distribution
"""

import sys
import os
import time
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.knowledge.loader import load_knowledge_base


# =============================================================================
# Тестовые запросы с ожидаемыми категориями/топиками
# =============================================================================
# (query, expected_category, expected_topic_substring)
# expected_topic_substring — подстрока которая ДОЛЖНА быть в topic или facts найденной секции

TEST_QUERIES = [
    # Pricing
    ("сколько стоит вообще ваша система?", "pricing", "цен"),
    ("ну и сколько это стоит на 3 точки?", "pricing", "точ"),
    ("сколько стоит сама программа?", "pricing", "цен"),
    ("а если на год то скидка есть какая нибудь?", "pricing", "скидк"),
    ("какие тарифы у вас есть?", "pricing", "тариф"),
    ("есть рассрочка?", "pricing", "рассроч"),

    # Equipment
    ("вам нужен интернет для кассы? Проводной или беспроводной?", "equipment", "интернет"),
    ("принтер этикеток нужен чтобы распечатать штрихкоды на товары?", "equipment", "принтер"),
    ("а весы пока обычные можно использовать?", "equipment", "вес"),
    ("какой моноблок посоветуете?", "equipment", "моноблок"),

    # Features
    ("у вас есть складской учет?", "inventory", "склад"),
    ("ревизия у нас 2 дня занимает каждый месяц, у вас быстрее?", "inventory", "ревизи"),
    ("можно отправлять электронные чеки клиентам?", "fiscal", "чек"),
    ("поддержка размерной сетки и различных типов товаров?", "features", "размер"),

    # Integrations
    ("а данные с 1с можно перенести к вам?", "integrations", "1с"),
    ("маркировку поддерживаете? у нас же лекарства", "integrations", "маркировк"),
    ("у вас есть интеграция с pos-терминалами?", "integrations", "pos"),
    ("kaspi qr подключается?", "integrations", "kaspi"),

    # Support & Delivery
    ("сколько занимает доставка?", "delivery", "доставк"),
    ("сопровождение с вас есть, и как долго?", "support", "поддержк"),
    ("Нужна ли поддержка при подключении?", "support", "подключ"),

    # Product info
    ("Wipon это программа или оборудование?", "products", "wipon"),
    ("чем вы лучше poster?", "competitors", "poster"),
    ("чем отличается Mini от Standard?", "products", "mini"),

    # Complex / multi-topic
    ("сколько стоит комплект оборудования с моноблоком?", "pricing", "моноблок"),
    ("как работает офлайн режим если интернет пропадёт?", "mobile", "офлайн"),
    ("какие банки поддерживают рассрочку через вас?", "pricing", "банк"),
    ("можно ли вести учёт нескольких магазинов в одной программе?", "products", "точ"),
    ("как добавить сотрудника и ограничить ему доступ?", "employees", "сотрудник"),
    ("аналитика продаж есть? abc анализ?", "analytics", "abc"),
]


@dataclass
class SearchHit:
    rank: int
    category: str
    topic: str
    score: float
    facts_preview: str


def encode_sections_frida(model, sections, use_prefixes=True):
    """Encode KB sections using FRIDA format."""
    if use_prefixes:
        texts = [
            f"search_document: [{s.category}/{s.topic}] "
            f"({', '.join(s.keywords[:5])}). {s.facts}"
            for s in sections
        ]
    else:
        texts = [s.facts for s in sections]

    print(f"  Encoding {len(texts)} sections...")
    t0 = time.time()
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=64)
    dt = time.time() - t0
    print(f"  Done in {dt:.1f}s ({len(texts)/dt:.0f} sections/s)")
    return embeddings


def encode_sections_qwen3(model, sections):
    """Encode KB sections using Qwen3 format (no special prefix)."""
    texts = [s.facts for s in sections]

    print(f"  Encoding {len(texts)} sections...")
    t0 = time.time()
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=32)
    dt = time.time() - t0
    print(f"  Done in {dt:.1f}s ({len(texts)/dt:.0f} sections/s)")
    return embeddings


def encode_query_frida(model, query):
    """Encode query using FRIDA prefix."""
    return model.encode(f"search_query: {query}")


def encode_query_qwen3(model, query, task_instruction=None):
    """Encode query using Qwen3 instruction format."""
    if task_instruction:
        return model.encode(query, prompt_name="query")
    return model.encode(query)


def search_topk(query_emb, section_embs, sections, top_k=10):
    """Cosine similarity search, return top-K hits."""
    # Normalize
    q_norm = query_emb / np.linalg.norm(query_emb)
    s_norms = section_embs / np.linalg.norm(section_embs, axis=1, keepdims=True)

    scores = s_norms @ q_norm
    top_indices = np.argsort(scores)[::-1][:top_k]

    hits = []
    for rank, idx in enumerate(top_indices):
        s = sections[idx]
        hits.append(SearchHit(
            rank=rank + 1,
            category=s.category,
            topic=s.topic,
            score=float(scores[idx]),
            facts_preview=s.facts[:120].replace('\n', ' '),
        ))
    return hits


def is_hit(hits: List[SearchHit], expected_category: str, expected_substr: str, top_k: int) -> bool:
    """Check if expected result is in top-K."""
    for h in hits[:top_k]:
        if h.category == expected_category or expected_substr.lower() in h.facts_preview.lower():
            return True
        if expected_substr.lower() in h.topic.lower():
            return True
    return False


def reciprocal_rank(hits: List[SearchHit], expected_category: str, expected_substr: str) -> float:
    """Get reciprocal rank of first relevant hit."""
    for h in hits:
        if h.category == expected_category or expected_substr.lower() in h.facts_preview.lower():
            return 1.0 / h.rank
        if expected_substr.lower() in h.topic.lower():
            return 1.0 / h.rank
    return 0.0


def run_comparison():
    print("=" * 70)
    print("FRIDA vs Qwen3-Embedding-4B — Comparison on real KB queries")
    print("=" * 70)

    # Load KB
    print("\n[1/5] Loading knowledge base...")
    kb = load_knowledge_base()
    sections = kb.sections
    print(f"  {len(sections)} sections loaded")

    # Load FRIDA
    print("\n[2/5] Loading FRIDA (ai-forever/FRIDA)...")
    from sentence_transformers import SentenceTransformer
    t0 = time.time()
    frida = SentenceTransformer("ai-forever/FRIDA", device="cuda")
    print(f"  Loaded in {time.time()-t0:.1f}s")

    # Load Qwen3-Embedding-4B
    print("\n[3/5] Loading Qwen3-Embedding-4B (will download if needed)...")
    t0 = time.time()
    qwen3 = SentenceTransformer("Qwen/Qwen3-Embedding-4B", device="cuda")
    print(f"  Loaded in {time.time()-t0:.1f}s")

    # Encode sections
    print("\n[4/5] Encoding KB sections...")
    print("  --- FRIDA ---")
    frida_embs = encode_sections_frida(frida, sections)
    print("  --- Qwen3-4B ---")
    qwen3_embs = encode_sections_qwen3(qwen3, sections)

    # Run queries
    print(f"\n[5/5] Running {len(TEST_QUERIES)} test queries...")
    print()

    results_frida = {"hr1": 0, "hr3": 0, "hr5": 0, "rr_sum": 0.0}
    results_qwen3 = {"hr1": 0, "hr3": 0, "hr5": 0, "rr_sum": 0.0}

    details = []

    for i, (query, exp_cat, exp_substr) in enumerate(TEST_QUERIES):
        # FRIDA
        q_frida = encode_query_frida(frida, query)
        hits_frida = search_topk(q_frida, frida_embs, sections, top_k=10)

        # Qwen3
        q_qwen3 = encode_query_qwen3(qwen3, query)
        hits_qwen3 = search_topk(q_qwen3, qwen3_embs, sections, top_k=10)

        # Metrics
        for k in [1, 3, 5]:
            if is_hit(hits_frida, exp_cat, exp_substr, k):
                results_frida[f"hr{k}"] += 1
            if is_hit(hits_qwen3, exp_cat, exp_substr, k):
                results_qwen3[f"hr{k}"] += 1

        rr_f = reciprocal_rank(hits_frida, exp_cat, exp_substr)
        rr_q = reciprocal_rank(hits_qwen3, exp_cat, exp_substr)
        results_frida["rr_sum"] += rr_f
        results_qwen3["rr_sum"] += rr_q

        # Winner for this query
        winner = "=" if rr_f == rr_q else ("FRIDA" if rr_f > rr_q else "Qwen3")

        detail = {
            "query": query,
            "expected": f"{exp_cat}/{exp_substr}",
            "frida_top1": f"{hits_frida[0].category}/{hits_frida[0].topic} ({hits_frida[0].score:.3f})",
            "qwen3_top1": f"{hits_qwen3[0].category}/{hits_qwen3[0].topic} ({hits_qwen3[0].score:.3f})",
            "frida_rr": rr_f,
            "qwen3_rr": rr_q,
            "winner": winner,
        }
        details.append(detail)

        # Print per-query result
        status_f = "v" if rr_f > 0 else "X"
        status_q = "v" if rr_q > 0 else "X"
        print(f"  [{i+1:2d}] {query[:55]:<55s}")
        print(f"       FRIDA [{status_f}] top1: {hits_frida[0].category}/{hits_frida[0].topic[:30]} ({hits_frida[0].score:.3f})")
        print(f"       Qwen3 [{status_q}] top1: {hits_qwen3[0].category}/{hits_qwen3[0].topic[:30]} ({hits_qwen3[0].score:.3f})")
        if winner != "=":
            print(f"       >>> Winner: {winner}")
        print()

    # Summary
    n = len(TEST_QUERIES)
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"{'Metric':<25s} {'FRIDA':>10s} {'Qwen3-4B':>10s} {'Delta':>10s}")
    print("-" * 55)

    for label, key in [("Hit Rate @1", "hr1"), ("Hit Rate @3", "hr3"), ("Hit Rate @5", "hr5")]:
        f_val = results_frida[key] / n * 100
        q_val = results_qwen3[key] / n * 100
        delta = q_val - f_val
        sign = "+" if delta > 0 else ""
        print(f"{label:<25s} {f_val:>9.1f}% {q_val:>9.1f}% {sign}{delta:>8.1f}%")

    mrr_f = results_frida["rr_sum"] / n
    mrr_q = results_qwen3["rr_sum"] / n
    delta_mrr = mrr_q - mrr_f
    sign = "+" if delta_mrr > 0 else ""
    print(f"{'MRR':<25s} {mrr_f:>10.3f} {mrr_q:>10.3f} {sign}{delta_mrr:>9.3f}")

    # Count wins
    frida_wins = sum(1 for d in details if d["winner"] == "FRIDA")
    qwen3_wins = sum(1 for d in details if d["winner"] == "Qwen3")
    ties = sum(1 for d in details if d["winner"] == "=")
    print(f"\n{'Wins':<25s} {frida_wins:>10d} {qwen3_wins:>10d} {'ties: ' + str(ties):>10s}")

    # Queries where one model failed and other succeeded
    print("\n" + "=" * 70)
    print("DIVERGENT RESULTS (one found, other missed)")
    print("=" * 70)
    for d in details:
        if (d["frida_rr"] > 0) != (d["qwen3_rr"] > 0):
            found_by = "FRIDA" if d["frida_rr"] > 0 else "Qwen3"
            print(f"  [{found_by} only] {d['query'][:60]}")
            print(f"    Expected: {d['expected']}")
            print(f"    FRIDA: {d['frida_top1']}")
            print(f"    Qwen3: {d['qwen3_top1']}")
            print()

    print("\nDone!")


if __name__ == "__main__":
    run_comparison()
