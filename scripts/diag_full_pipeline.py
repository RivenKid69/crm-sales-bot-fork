#!/usr/bin/env python3
"""
Diagnostic: simulate the FULL retrieval pipeline for each failing turn
with actual dialog history, rewrite, state backfill, and merge.
Shows exactly what lands in {retrieved_facts} for the LLM.
"""
import sys, os, json, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.knowledge.enhanced_retrieval import EnhancedRetrievalPipeline
from src.knowledge.retriever import get_retriever

# Load the audit data
with open("results/deep_audit_10_20260226_102458.json") as f:
    audit = json.load(f)

# Define the failing turns with correct scenario + turn index
CASES = [
    # (scenario_idx, turn_idx, tag, expected_topic)
    (1, 7, "D02-T8", "support response time"),       # "отвечали по 3 дня"
    (3, 4, "D04-T5", "marking module pricing"),       # "сколько это стоит"
    (5, 6, "D06-T7", "Kaspi marketplace integration"),# "Kaspi маркетплейсом"
    (5, 9, "D06-T10", "remote/onsite setup"),         # "настройку оборудования"
    (6, 6, "D07-T7", "WhatsApp integration"),         # "WhatsApp для рассылки"
    (6, 7, "D07-T8", "retail product overview"),      # "что реально есть"
]


def build_history(scenario, up_to_turn_idx):
    """Build history list from scenario turns, up to (not including) the target turn."""
    history = []
    for t in scenario["turns"][:up_to_turn_idx]:
        history.append({"role": "user", "content": t["user"]})
        history.append({"role": "assistant", "content": t["bot"]})
    return history


def main():
    retriever = get_retriever()
    kb = retriever.kb

    # Lazy-init LLM for rewrite
    from src.llm import OllamaClient
    llm = OllamaClient()

    pipeline = EnhancedRetrievalPipeline(llm=llm, category_router=None)

    # Load flow config
    from src.config_loader import ConfigLoader
    loader = ConfigLoader()
    flow_config = loader.load_flow("autonomous")

    results = []

    for scenario_idx, turn_idx, tag, expected_topic in CASES:
        scenario = audit["scenarios"][scenario_idx]
        turn = scenario["turns"][turn_idx]
        user_msg = turn["user"]
        state = turn["state"]
        intent = turn["intent"]
        bot_response = turn["bot"]

        history = build_history(scenario, turn_idx)

        print(f"\n{'='*90}")
        print(f"  {tag}: \"{user_msg[:80]}\"")
        print(f"  state={state}  intent={intent}")
        print(f"  expected_topic={expected_topic}")
        print(f"  bot_response={bot_response[:120]}...")
        print(f"{'='*90}")

        # Run the full pipeline
        retrieved_facts, urls, fact_keys = pipeline.retrieve(
            user_message=user_msg,
            intent=intent,
            state=state,
            flow_config=flow_config,
            kb=kb,
            recently_used_keys=set(),  # no rotation for diagnostic
            history=history,
            secondary_intents=[],
            collected_data={},
        )

        # Check rewrite
        rewritten = pipeline.query_rewriter.rewrite(user_msg, history)
        rewrite_changed = rewritten != user_msg.strip()

        print(f"\n  --- QUERY REWRITE ---")
        print(f"    original:  \"{user_msg}\"")
        print(f"    rewritten: \"{rewritten}\"")
        print(f"    changed:   {rewrite_changed}")

        print(f"\n  --- FACT KEYS ({len(fact_keys)}) ---")
        for i, key in enumerate(fact_keys[:15]):
            marker = ""
            print(f"    [{i+1}] {key}{marker}")

        # Show first N chars of retrieved_facts
        print(f"\n  --- RETRIEVED_FACTS ({len(retrieved_facts)} chars) ---")
        # Show first 1500 chars
        preview = retrieved_facts[:1500]
        for line in preview.split("\n"):
            print(f"    {line[:120]}")
        if len(retrieved_facts) > 1500:
            print(f"    ... ({len(retrieved_facts) - 1500} more chars)")

        # Check if === КОНТЕКСТ ЭТАПА === separator exists
        if "=== КОНТЕКСТ ЭТАПА ===" in retrieved_facts:
            sep_pos = retrieved_facts.index("=== КОНТЕКСТ ЭТАПА ===")
            query_part = retrieved_facts[:sep_pos]
            state_part = retrieved_facts[sep_pos:]
            print(f"\n  --- SPLIT ---")
            print(f"    query-driven:  {len(query_part)} chars")
            print(f"    state backfill: {len(state_part)} chars")
        else:
            print(f"\n  --- SPLIT ---")
            print(f"    (no separator — all query-driven or all state backfill)")

        results.append({
            "tag": tag,
            "user_msg": user_msg,
            "state": state,
            "intent": intent,
            "bot_response": bot_response,
            "rewrite_changed": rewrite_changed,
            "rewritten_query": rewritten,
            "fact_keys": fact_keys,
            "retrieved_facts_len": len(retrieved_facts),
            "retrieved_facts_first_2k": retrieved_facts[:2000],
        })

    out_path = "results/diag_full_pipeline.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n\nSaved to {out_path}")


if __name__ == "__main__":
    main()
