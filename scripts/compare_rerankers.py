#!/usr/bin/env python3
"""
Сравнение реранкеров: BGE-reranker-v2-m3 (текущий) vs Qwen3-Reranker-4B

Методика:
1. FRIDA находит top-20 кандидатов (как в реальном pipeline)
2. Оба реранкера переоценивают одних и тех же 20 кандидатов
3. Сравниваем: кто лучше выводит релевантную секцию в top-1/3/5

Фокус на СЛОЖНЫХ запросах где FRIDA даёт неоднозначные результаты.
"""

import sys
import os
import time
import json
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.knowledge.loader import load_knowledge_base

# =============================================================================
# Сложные тестовые запросы — акцент на неоднозначных и multi-topic
# =============================================================================
# (query, expected_keywords_in_best_result)
# expected_keywords — слова которые ДОЛЖНЫ быть в facts лучшего результата

TEST_QUERIES = [
    # --- Pricing: сложные ---
    ("сколько стоит подключение на 5 точек?",
     ["точ", "цен", "стоимост"]),
    ("а если 10 касс нужно, какая цена за год?",
     ["цен", "год", "касс"]),
    ("мне нужно 3 магазина по тарифу Standard, сколько выйдет?",
     ["standard", "цен", "магазин"]),
    ("рассрочка через каспи есть? на какой срок?",
     ["рассроч", "kaspi", "каспи"]),
    ("скидка при оплате за 2 года вперёд?",
     ["скидк", "год"]),

    # --- Equipment: неоднозначные ---
    ("у меня маленький магазин 30 кв.м, какое оборудование подойдёт?",
     ["магазин", "оборудовани", "комплект"]),
    ("можно только программу без оборудования взять?",
     ["программ", "без", "оборудовани"]),
    ("моноблок или планшет, что лучше для кафе?",
     ["моноблок", "планшет"]),
    ("сканер штрихкодов беспроводной есть у вас?",
     ["сканер", "штрихкод", "беспровод"]),
    ("нужен принтер чеков + денежный ящик, есть комплектом?",
     ["принтер", "чек", "денежн", "ящик"]),

    # --- Integrations: специфичные ---
    ("работаете с маркировкой обуви через честный знак?",
     ["маркировк", "обув", "честный знак"]),
    ("можно интегрировать с моей 1С бухгалтерией?",
     ["1с", "интеграц", "бухгалтер"]),
    ("есть подключение к kaspi магазину для онлайн продаж?",
     ["kaspi", "каспи", "магазин", "онлайн"]),
    ("ЭСФ и СНТ поддерживаете?",
     ["эсф", "снт", "электронн"]),
    ("NFC оплата через телефон клиента работает?",
     ["nfc", "бесконтакт", "оплат"]),

    # --- Features: сложные вопросы ---
    ("как контролировать кассира чтобы не воровал?",
     ["кассир", "контрол", "доступ"]),
    ("можно настроить автоматический заказ товара при минимальном остатке?",
     ["заказ", "остат", "автомат"]),
    ("у нас сезонные товары, можно менять цены массово?",
     ["цен", "массов", "изменен"]),
    ("а если интернет пропадёт, данные не потеряются?",
     ["интернет", "офлайн", "данн", "синхрониз"]),
    ("можно вести учёт по серийным номерам? у нас электроника",
     ["серийн", "номер", "учёт"]),

    # --- Support & Delivery ---
    ("как быстро доставите в Актау?",
     ["доставк", "актау", "срок"]),
    ("если оборудование сломается, как гарантия работает?",
     ["гарант", "ремонт", "замен"]),
    ("обучение сотрудников входит в стоимость?",
     ["обучен", "стоимост", "сотрудник"]),
    ("техподдержка 24/7 или по графику?",
     ["поддержк", "24", "график", "время"]),

    # --- Competitors ---
    ("чем вы лучше poster? у них дешевле",
     ["poster", "преимущ", "дешев"]),
    ("я сейчас на iiko, почему мне переходить к вам?",
     ["iiko", "переход", "преимущ"]),

    # --- Kazakh / mixed ---
    ("бағасы қанша 2 дүкенге?",
     ["цен", "стоимост", "точ", "магазин"]),
    ("маған тариф Mini жеткілікті ме?",
     ["mini", "тариф"]),

    # --- Multi-intent / complex ---
    ("у меня аптека, нужен учёт лекарств с маркировкой и сроками годности",
     ["аптек", "маркировк", "срок", "годност"]),
    ("хочу открыть сеть из 5 магазинов одежды, что посоветуете полностью?",
     ["сеть", "магазин", "одежд"]),
]


def frida_get_candidates(frida_model, sections, query, top_k=20):
    """Get top-K candidates using FRIDA (same as production pipeline)."""
    # Encode query
    q_emb = frida_model.encode(f"search_query: {query}")
    q_norm = q_emb / np.linalg.norm(q_emb)

    # Score all sections
    scores = []
    for i, s in enumerate(sections):
        s_emb = np.array(s.embedding)
        s_norm = s_emb / np.linalg.norm(s_emb)
        score = float(np.dot(q_norm, s_norm))
        scores.append((i, score))

    scores.sort(key=lambda x: x[1], reverse=True)
    return [(sections[i], sc) for i, sc in scores[:top_k]]


def rerank_bge(model, query, candidates):
    """Rerank using BGE cross-encoder."""
    pairs = [(query, c.facts) for c, _ in candidates]
    scores = model.predict(pairs)
    results = list(zip(candidates, scores))
    results.sort(key=lambda x: x[1], reverse=True)
    return [(c, orig_sc, float(new_sc)) for (c, orig_sc), new_sc in results]


def _init_qwen3_reranker():
    """Load Qwen3-Reranker-4B using official inference method (CausalLM + yes/no logits)."""
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM

    tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen3-Reranker-4B", padding_side='left')
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        "Qwen/Qwen3-Reranker-4B",
        dtype=torch.float16,
    ).cuda().eval()

    token_false_id = tokenizer.convert_tokens_to_ids("no")
    token_true_id = tokenizer.convert_tokens_to_ids("yes")

    prefix = "<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct provided. Note that the answer can only be \"yes\" or \"no\".<|im_end|>\n<|im_start|>user\n"
    suffix = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
    prefix_tokens = tokenizer.encode(prefix, add_special_tokens=False)
    suffix_tokens = tokenizer.encode(suffix, add_special_tokens=False)

    return {
        "tokenizer": tokenizer,
        "model": model,
        "token_true_id": token_true_id,
        "token_false_id": token_false_id,
        "prefix_tokens": prefix_tokens,
        "suffix_tokens": suffix_tokens,
        "max_length": 8192,
    }


def _format_qwen3_pair(instruction, query, doc):
    """Format a query-document pair for Qwen3-Reranker."""
    if instruction is None:
        instruction = "Given a web search query, retrieve relevant passages that answer the query"
    return f"<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {doc}"


def rerank_qwen3(qwen3_ctx, query, candidates, instruction=None):
    """Rerank using Qwen3-Reranker-4B (CausalLM yes/no logits method)."""
    import torch

    tokenizer = qwen3_ctx["tokenizer"]
    model = qwen3_ctx["model"]
    token_true_id = qwen3_ctx["token_true_id"]
    token_false_id = qwen3_ctx["token_false_id"]
    prefix_tokens = qwen3_ctx["prefix_tokens"]
    suffix_tokens = qwen3_ctx["suffix_tokens"]
    max_length = qwen3_ctx["max_length"]

    if instruction is None:
        instruction = "Дан поисковый запрос клиента, определи насколько документ из базы знаний релевантен запросу"

    pairs = [_format_qwen3_pair(instruction, query, c.facts) for c, _ in candidates]

    # Tokenize with prefix/suffix wrapping
    inputs = tokenizer(
        pairs, padding=False, truncation='longest_first',
        return_attention_mask=False,
        max_length=max_length - len(prefix_tokens) - len(suffix_tokens),
    )
    for i, ele in enumerate(inputs['input_ids']):
        inputs['input_ids'][i] = prefix_tokens + ele + suffix_tokens
    inputs = tokenizer.pad(inputs, padding=True, return_tensors="pt", max_length=max_length)
    for key in inputs:
        inputs[key] = inputs[key].to(model.device)

    with torch.no_grad():
        batch_scores = model(**inputs).logits[:, -1, :]
        true_vector = batch_scores[:, token_true_id]
        false_vector = batch_scores[:, token_false_id]
        batch_scores = torch.stack([false_vector, true_vector], dim=1)
        batch_scores = torch.nn.functional.log_softmax(batch_scores, dim=1)
        scores = batch_scores[:, 1].exp().tolist()

    results = list(zip(candidates, scores))
    results.sort(key=lambda x: x[1], reverse=True)
    return [(c, orig_sc, float(new_sc)) for (c, orig_sc), new_sc in results]


def relevance_score(section_facts: str, expected_keywords: List[str]) -> int:
    """Count how many expected keywords appear in facts."""
    facts_lower = section_facts.lower()
    return sum(1 for kw in expected_keywords if kw.lower() in facts_lower)


def find_best_rank(ranked_results, expected_keywords, top_k=10):
    """Find rank of first result matching expected keywords (1-indexed). 0 = not found."""
    for i, (section, _, _) in enumerate(ranked_results[:top_k]):
        if relevance_score(section.facts, expected_keywords) >= 2:
            return i + 1
    # Fallback: at least 1 keyword
    for i, (section, _, _) in enumerate(ranked_results[:top_k]):
        if relevance_score(section.facts, expected_keywords) >= 1:
            return i + 1
    return 0


def run_comparison():
    print("=" * 80)
    print("RERANKER COMPARISON: BGE-reranker-v2-m3 vs Qwen3-Reranker-4B")
    print("=" * 80)

    # Load KB
    print("\n[1/5] Loading knowledge base...")
    kb = load_knowledge_base()
    sections = kb.sections
    print(f"  {len(sections)} sections")

    # Load FRIDA for candidate retrieval
    print("\n[2/5] Loading FRIDA (for candidate retrieval)...")
    from sentence_transformers import SentenceTransformer, CrossEncoder
    frida = SentenceTransformer("ai-forever/FRIDA", device="cuda")

    # Pre-encode all sections with FRIDA
    print("  Encoding sections...")
    texts = [
        f"search_document: [{s.category}/{s.topic}] "
        f"({', '.join(s.keywords[:5])}). {s.facts}"
        for s in sections
    ]
    embeddings = frida.encode(texts, show_progress_bar=True, batch_size=64)
    for i, s in enumerate(sections):
        s.embedding = embeddings[i]
    print(f"  Done, {len(sections)} sections indexed")

    # Load BGE reranker (current)
    print("\n[3/5] Loading BGE-reranker-v2-m3 (current, CPU)...")
    t0 = time.time()
    bge = CrossEncoder("BAAI/bge-reranker-v2-m3", device="cpu")
    print(f"  Loaded in {time.time()-t0:.1f}s")

    # Load Qwen3-Reranker-4B via transformers (CausalLM + yes/no logits)
    print("\n[4/5] Loading Qwen3-Reranker-4B...")
    t0 = time.time()
    qwen3_ctx = _init_qwen3_reranker()
    print(f"  Loaded in {time.time()-t0:.1f}s")

    # Run comparison
    print(f"\n[5/5] Running {len(TEST_QUERIES)} complex queries...")
    print()

    stats_frida_only = {"hr1": 0, "hr3": 0, "hr5": 0, "rr": 0.0}
    stats_bge = {"hr1": 0, "hr3": 0, "hr5": 0, "rr": 0.0, "time": 0.0}
    stats_qwen3 = {"hr1": 0, "hr3": 0, "hr5": 0, "rr": 0.0, "time": 0.0}

    details = []

    for i, (query, expected_kw) in enumerate(TEST_QUERIES):
        # Get FRIDA candidates
        candidates = frida_get_candidates(frida, sections, query, top_k=20)

        # FRIDA-only ranking (no reranker)
        frida_ranked = [(c, sc, sc) for c, sc in candidates]
        frida_rank = find_best_rank(frida_ranked, expected_kw)

        # BGE reranking
        t0 = time.time()
        bge_ranked = rerank_bge(bge, query, candidates)
        bge_time = time.time() - t0
        bge_rank = find_best_rank(bge_ranked, expected_kw)

        # Qwen3 reranking
        t0 = time.time()
        qwen3_ranked = rerank_qwen3(qwen3_ctx, query, candidates)
        qwen3_time = time.time() - t0
        qwen3_rank = find_best_rank(qwen3_ranked, expected_kw)

        # Accumulate stats
        for stats, rank in [(stats_frida_only, frida_rank), (stats_bge, bge_rank), (stats_qwen3, qwen3_rank)]:
            if rank > 0:
                stats["rr"] += 1.0 / rank
                if rank <= 1: stats["hr1"] += 1
                if rank <= 3: stats["hr3"] += 1
                if rank <= 5: stats["hr5"] += 1
        stats_bge["time"] += bge_time
        stats_qwen3["time"] += qwen3_time

        # Determine winner
        if bge_rank == 0 and qwen3_rank == 0:
            winner = "BOTH_MISS"
        elif bge_rank == 0:
            winner = "Qwen3"
        elif qwen3_rank == 0:
            winner = "BGE"
        elif qwen3_rank < bge_rank:
            winner = "Qwen3"
        elif bge_rank < qwen3_rank:
            winner = "BGE"
        else:
            winner = "="

        detail = {
            "query": query,
            "expected_kw": expected_kw,
            "frida_rank": frida_rank,
            "bge_rank": bge_rank,
            "qwen3_rank": qwen3_rank,
            "bge_time": bge_time,
            "qwen3_time": qwen3_time,
            "winner": winner,
            "bge_top1_topic": f"{bge_ranked[0][0].category}/{bge_ranked[0][0].topic[:35]}",
            "qwen3_top1_topic": f"{qwen3_ranked[0][0].category}/{qwen3_ranked[0][0].topic[:35]}",
            "bge_top1_score": bge_ranked[0][2],
            "qwen3_top1_score": qwen3_ranked[0][2],
            "bge_top1_preview": bge_ranked[0][0].facts[:100].replace('\n', ' '),
            "qwen3_top1_preview": qwen3_ranked[0][0].facts[:100].replace('\n', ' '),
        }
        details.append(detail)

        # Print per-query
        f_sym = f"@{frida_rank}" if frida_rank > 0 else "MISS"
        b_sym = f"@{bge_rank}" if bge_rank > 0 else "MISS"
        q_sym = f"@{qwen3_rank}" if qwen3_rank > 0 else "MISS"

        print(f"  [{i+1:2d}] {query[:65]}")
        print(f"       Keywords: {expected_kw}")
        print(f"       FRIDA(no-rr): {f_sym:<6s}  BGE: {b_sym:<6s} ({bge_time*1000:.0f}ms)  Qwen3: {q_sym:<6s} ({qwen3_time*1000:.0f}ms)")
        if winner not in ("=", "BOTH_MISS"):
            print(f"       >>> Winner: {winner}")
        if bge_rank != qwen3_rank:
            print(f"       BGE  top1: {detail['bge_top1_topic']} ({detail['bge_top1_score']:.3f})")
            print(f"                  {detail['bge_top1_preview'][:90]}")
            print(f"       Qwen top1: {detail['qwen3_top1_topic']} ({detail['qwen3_top1_score']:.3f})")
            print(f"                  {detail['qwen3_top1_preview'][:90]}")
        print()

    # Summary
    n = len(TEST_QUERIES)
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"{'Metric':<25s} {'FRIDA only':>12s} {'BGE (curr)':>12s} {'Qwen3-4B':>12s}")
    print("-" * 61)

    for label, key in [("Hit Rate @1", "hr1"), ("Hit Rate @3", "hr3"), ("Hit Rate @5", "hr5")]:
        f_val = stats_frida_only[key] / n * 100
        b_val = stats_bge[key] / n * 100
        q_val = stats_qwen3[key] / n * 100
        print(f"{label:<25s} {f_val:>11.1f}% {b_val:>11.1f}% {q_val:>11.1f}%")

    mrr_f = stats_frida_only["rr"] / n
    mrr_b = stats_bge["rr"] / n
    mrr_q = stats_qwen3["rr"] / n
    print(f"{'MRR':<25s} {mrr_f:>12.3f} {mrr_b:>12.3f} {mrr_q:>12.3f}")

    avg_bge_ms = stats_bge["time"] / n * 1000
    avg_qwen3_ms = stats_qwen3["time"] / n * 1000
    print(f"{'Avg latency (20 docs)':<25s} {'---':>12s} {avg_bge_ms:>10.0f}ms {avg_qwen3_ms:>10.0f}ms")

    # Wins
    bge_wins = sum(1 for d in details if d["winner"] == "BGE")
    qwen3_wins = sum(1 for d in details if d["winner"] == "Qwen3")
    ties = sum(1 for d in details if d["winner"] == "=")
    both_miss = sum(1 for d in details if d["winner"] == "BOTH_MISS")
    print(f"\n{'Wins':<25s} {'---':>12s} {bge_wins:>12d} {qwen3_wins:>12d}")
    print(f"{'Ties':<25s} {'':>12s} {ties:>12d}")
    print(f"{'Both missed':<25s} {'':>12s} {both_miss:>12d}")

    # Divergent results
    print("\n" + "=" * 80)
    print("CASES WHERE MODELS DISAGREE (different rank)")
    print("=" * 80)
    for d in details:
        if d["bge_rank"] != d["qwen3_rank"]:
            b_sym = f"@{d['bge_rank']}" if d['bge_rank'] > 0 else "MISS"
            q_sym = f"@{d['qwen3_rank']}" if d['qwen3_rank'] > 0 else "MISS"
            print(f"  [{d['winner']:>5s}] {d['query'][:60]}")
            print(f"         BGE {b_sym} → {d['bge_top1_topic']}")
            print(f"         Qwen3 {q_sym} → {d['qwen3_top1_topic']}")
            print()

    # Qwen3 improvement over BGE
    print("=" * 80)
    improvement = (stats_qwen3["rr"] - stats_bge["rr"]) / max(stats_bge["rr"], 0.001) * 100
    print(f"Qwen3-4B MRR improvement over BGE: {improvement:+.1f}%")
    print(f"Qwen3-4B wins: {qwen3_wins}, BGE wins: {bge_wins}, Ties: {ties}")
    print("=" * 80)


if __name__ == "__main__":
    run_comparison()
