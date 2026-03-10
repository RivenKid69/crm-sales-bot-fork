#!/usr/bin/env python3
"""
Полное сравнение 5 pipeline конфигураций:

  A) FRIDA only (no reranker)
  E) FRIDA + BGE-reranker (ТЕКУЩИЙ ПРОД)
  B) FRIDA + Qwen3-Reranker-4B
  C) Qwen3-Embed-4B only (no reranker)
  D) Qwen3-Embed-4B + Qwen3-Reranker-4B (full TEI stack)
"""

import sys
import os
import time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.knowledge.loader import load_knowledge_base

TEST_QUERIES = [
    # Simple
    ("сколько стоит вообще ваша система?", "pricing", "цен"),
    ("ну и сколько это стоит на 3 точки?", "pricing", "точ"),
    ("а если на год то скидка есть какая нибудь?", "pricing", "скидк"),
    ("какие тарифы у вас есть?", "pricing", "тариф"),
    ("есть рассрочка?", "pricing", "рассроч"),
    ("вам нужен интернет для кассы?", "equipment", "интернет"),
    ("принтер этикеток нужен чтобы распечатать штрихкоды на товары?", "equipment", "принтер"),
    ("какой моноблок посоветуете?", "equipment", "моноблок"),
    ("у вас есть складской учет?", "inventory", "склад"),
    ("ревизия у нас 2 дня занимает каждый месяц, у вас быстрее?", "inventory", "ревизи"),
    ("можно отправлять электронные чеки клиентам?", "fiscal", "чек"),
    ("а данные с 1с можно перенести к вам?", "integrations", "1с"),
    ("маркировку поддерживаете? у нас же лекарства", "integrations", "маркировк"),
    ("kaspi qr подключается?", "integrations", "kaspi"),
    ("сколько занимает доставка?", "delivery", "доставк"),
    ("чем вы лучше poster?", "competitors", "poster"),
    ("чем отличается Mini от Standard?", "products", "mini"),
    ("как работает офлайн режим если интернет пропадёт?", "mobile", "офлайн"),
    ("как добавить сотрудника и ограничить ему доступ?", "employees", "сотрудник"),
    ("аналитика продаж есть? abc анализ?", "analytics", "abc"),
    # Complex
    ("сколько стоит подключение на 5 точек?", "pricing", "точ"),
    ("а если 10 касс нужно, какая цена за год?", "pricing", "касс"),
    ("рассрочка через каспи есть? на какой срок?", "pricing", "рассроч"),
    ("у меня маленький магазин 30 кв.м, какое оборудование подойдёт?", "equipment", "оборудовани"),
    ("можно только программу без оборудования взять?", "equipment", "программ"),
    ("моноблок или планшет, что лучше для кафе?", "equipment", "моноблок"),
    ("работаете с маркировкой обуви через честный знак?", "integrations", "маркировк"),
    ("можно интегрировать с моей 1С бухгалтерией?", "integrations", "1с"),
    ("есть подключение к kaspi магазину для онлайн продаж?", "integrations", "kaspi"),
    ("как контролировать кассира чтобы не воровал?", "employees", "кассир"),
    ("можно настроить автоматический заказ товара при минимальном остатке?", "inventory", "заказ"),
    ("а если интернет пропадёт, данные не потеряются?", "mobile", "офлайн"),
    ("если оборудование сломается, как гарантия работает?", "equipment", "гарант"),
    ("техподдержка 24/7 или по графику?", "support", "поддержк"),
    ("чем вы лучше poster? у них дешевле", "competitors", "poster"),
    ("я сейчас на iiko, почему мне переходить к вам?", "competitors", "iiko"),
    ("бағасы қанша 2 дүкенге?", "pricing", "цен"),
    ("маған тариф Mini жеткілікті ме?", "products", "mini"),
    ("у меня аптека, нужен учёт лекарств с маркировкой и сроками годности", "integrations", "маркировк"),
    ("хочу открыть сеть из 5 магазинов одежды, что посоветуете полностью?", "products", "магазин"),
]


def is_relevant(section, exp_cat, exp_substr):
    if section.category == exp_cat:
        return True
    if exp_substr.lower() in section.facts.lower():
        return True
    if exp_substr.lower() in section.topic.lower():
        return True
    return False


def get_top_k(query_emb, section_embs, sections, top_k):
    q_norm = query_emb / np.linalg.norm(query_emb)
    s_norms = section_embs / np.linalg.norm(section_embs, axis=1, keepdims=True)
    scores = s_norms @ q_norm
    top_indices = np.argsort(scores)[::-1][:top_k]
    return [(sections[idx], float(scores[idx])) for idx in top_indices]


def find_rank(ranked, exp_cat, exp_substr, top_k=10):
    for i, (section, _) in enumerate(ranked[:top_k]):
        if is_relevant(section, exp_cat, exp_substr):
            return i + 1
    return 0


def rerank_bge(bge_model, query, candidates):
    """Rerank with BGE cross-encoder."""
    pairs = [(query, s.facts) for s, _ in candidates]
    scores = bge_model.predict(pairs)
    results = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
    return [(s, float(sc)) for (s, _), sc in results]


def rerank_qwen3(qwen3_ctx, query, candidates):
    """Rerank with Qwen3-Reranker-4B."""
    import torch

    tokenizer = qwen3_ctx["tokenizer"]
    model = qwen3_ctx["model"]
    prefix_tokens = qwen3_ctx["prefix_tokens"]
    suffix_tokens = qwen3_ctx["suffix_tokens"]
    max_length = qwen3_ctx["max_length"]

    instruction = "Дан поисковый запрос клиента, определи насколько документ из базы знаний релевантен запросу"
    pairs = [
        f"<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {s.facts}"
        for s, _ in candidates
    ]

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
        true_vector = batch_scores[:, qwen3_ctx["token_true_id"]]
        false_vector = batch_scores[:, qwen3_ctx["token_false_id"]]
        batch_scores = torch.stack([false_vector, true_vector], dim=1)
        batch_scores = torch.nn.functional.log_softmax(batch_scores, dim=1)
        scores = batch_scores[:, 1].exp().tolist()

    results = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
    return [(s, float(sc)) for (s, _), sc in results]


def run():
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from sentence_transformers import SentenceTransformer, CrossEncoder

    print("=" * 85)
    print("FULL PIPELINE COMPARISON — 5 configurations")
    print("=" * 85)

    # --- Phase 1: Load KB and encode everything ---
    print("\n[1/5] Loading knowledge base...")
    kb = load_knowledge_base()
    sections = kb.sections
    print(f"  {len(sections)} sections")

    # FRIDA
    print("\n[2/5] FRIDA: encoding sections + queries...")
    frida = SentenceTransformer("ai-forever/FRIDA", device="cuda")
    frida_sec_texts = [
        f"search_document: [{s.category}/{s.topic}] "
        f"({', '.join(s.keywords[:5])}). {s.facts}"
        for s in sections
    ]
    frida_sec_embs = frida.encode(frida_sec_texts, show_progress_bar=True, batch_size=64)
    frida_query_embs = [frida.encode(f"search_query: {q}") for q, _, _ in TEST_QUERIES]
    del frida
    torch.cuda.empty_cache()
    print("  Done")

    # Qwen3-Embedding
    print("\n[3/5] Qwen3-Embedding-4B: encoding sections + queries...")
    qwen3e = SentenceTransformer("Qwen/Qwen3-Embedding-4B", device="cuda")
    qwen3_sec_embs = qwen3e.encode([s.facts for s in sections], show_progress_bar=True, batch_size=32)
    qwen3_query_embs = [qwen3e.encode(q) for q, _, _ in TEST_QUERIES]
    del qwen3e
    torch.cuda.empty_cache()
    print("  Done")

    # BGE reranker
    print("\n[4/5] Loading BGE-reranker-v2-m3 (current production, CPU)...")
    bge = CrossEncoder("BAAI/bge-reranker-v2-m3", device="cpu")
    print("  Done")

    # Qwen3-Reranker
    print("\n[5/5] Loading Qwen3-Reranker-4B (GPU)...")
    tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen3-Reranker-4B", padding_side='left')
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    reranker = AutoModelForCausalLM.from_pretrained(
        "Qwen/Qwen3-Reranker-4B", dtype=torch.float16
    ).cuda().eval()

    prefix = '<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct provided. Note that the answer can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
    suffix = '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'
    qwen3_ctx = {
        "tokenizer": tokenizer, "model": reranker,
        "token_true_id": tokenizer.convert_tokens_to_ids("yes"),
        "token_false_id": tokenizer.convert_tokens_to_ids("no"),
        "prefix_tokens": tokenizer.encode(prefix, add_special_tokens=False),
        "suffix_tokens": tokenizer.encode(suffix, add_special_tokens=False),
        "max_length": 8192,
    }
    print("  Done")

    # --- Phase 2: Evaluate ---
    n = len(TEST_QUERIES)
    print(f"\n{'='*85}")
    print(f"Running {n} queries x 5 pipelines...")
    print(f"  A: FRIDA only | E: FRIDA+BGE (prod) | B: FRIDA+Qwen3RR | C: Qwen3E only | D: Qwen3E+Qwen3RR")
    print(f"{'='*85}\n")

    KEYS = ["A", "E", "B", "C", "D"]
    stats = {k: {"hr1": 0, "hr3": 0, "hr5": 0, "rr": 0.0, "r20": 0} for k in KEYS}

    for i, (query, exp_cat, exp_substr) in enumerate(TEST_QUERIES):
        frida_cands = get_top_k(frida_query_embs[i], frida_sec_embs, sections, 20)
        qwen3_cands = get_top_k(qwen3_query_embs[i], qwen3_sec_embs, sections, 20)

        fr20 = any(is_relevant(s, exp_cat, exp_substr) for s, _ in frida_cands)
        qr20 = any(is_relevant(s, exp_cat, exp_substr) for s, _ in qwen3_cands)

        # A: FRIDA only
        rank_a = find_rank(frida_cands, exp_cat, exp_substr)
        # E: FRIDA + BGE (current prod)
        rank_e = find_rank(rerank_bge(bge, query, frida_cands), exp_cat, exp_substr)
        # B: FRIDA + Qwen3-Reranker
        rank_b = find_rank(rerank_qwen3(qwen3_ctx, query, frida_cands), exp_cat, exp_substr)
        # C: Qwen3-Embed only
        rank_c = find_rank(qwen3_cands, exp_cat, exp_substr)
        # D: Qwen3-Embed + Qwen3-Reranker
        rank_d = find_rank(rerank_qwen3(qwen3_ctx, query, qwen3_cands), exp_cat, exp_substr)

        ranks = {"A": rank_a, "E": rank_e, "B": rank_b, "C": rank_c, "D": rank_d}

        for k in KEYS:
            r = ranks[k]
            if k in ("A", "E", "B"):
                stats[k]["r20"] += int(fr20)
            else:
                stats[k]["r20"] += int(qr20)
            if r > 0:
                stats[k]["rr"] += 1.0 / r
                if r <= 1: stats[k]["hr1"] += 1
                if r <= 3: stats[k]["hr3"] += 1
                if r <= 5: stats[k]["hr5"] += 1

        def sym(r): return f"@{r}" if r > 0 else "X "
        print(f"  [{i+1:2d}] {query[:52]:<52s}  "
              f"A:{sym(rank_a):<4s} E:{sym(rank_e):<4s} B:{sym(rank_b):<4s} "
              f"C:{sym(rank_c):<4s} D:{sym(rank_d)}")

    # --- Summary ---
    print(f"\n{'='*85}")
    print("RESULTS")
    print(f"{'='*85}")
    print(f"{'Pipeline':<42s} {'HR@1':>7s} {'HR@3':>7s} {'HR@5':>7s} {'MRR':>7s} {'R@20':>6s}")
    print("-" * 78)

    labels = {
        "A": "A: FRIDA only (no reranker)",
        "E": "E: FRIDA + BGE (CURRENT PROD)",
        "B": "B: FRIDA + Qwen3-Reranker",
        "C": "C: Qwen3-Embed only (no reranker)",
        "D": "D: Qwen3-Embed + Qwen3-Reranker (TEI)",
    }
    for key in ["A", "E", "B", "C", "D"]:
        s = stats[key]
        marker = " <<<" if key == "E" else ""
        print(f"{labels[key]:<42s} {s['hr1']/n*100:>6.1f}% {s['hr3']/n*100:>6.1f}% "
              f"{s['hr5']/n*100:>6.1f}% {s['rr']/n:>7.3f} {s['r20']/n*100:>5.1f}%{marker}")

    # Comparisons
    print(f"\n{'='*85}")
    print("COMPARISONS")
    print(f"{'='*85}")

    def fmt(key):
        s = stats[key]
        return f"HR@1={s['hr1']/n*100:.1f}% MRR={s['rr']/n:.3f}"

    e_mrr = stats["E"]["rr"] / n
    b_mrr = stats["B"]["rr"] / n
    d_mrr = stats["D"]["rr"] / n

    print(f"\n  Current prod (E):           {fmt('E')}")
    print(f"  Upgrade reranker (B):       {fmt('B')}  ({(b_mrr-e_mrr)/e_mrr*100:+.1f}% MRR vs prod)")
    print(f"  Full TEI stack (D):         {fmt('D')}  ({(d_mrr-e_mrr)/e_mrr*100:+.1f}% MRR vs prod)")
    print(f"\n  B vs E (just swap reranker): HR@1 {(stats['B']['hr1']-stats['E']['hr1'])/n*100:+.1f}pp, MRR {b_mrr-e_mrr:+.3f}")
    print(f"  D vs E (full TEI swap):      HR@1 {(stats['D']['hr1']-stats['E']['hr1'])/n*100:+.1f}pp, MRR {d_mrr-e_mrr:+.3f}")
    print(f"{'='*85}")


if __name__ == "__main__":
    run()
