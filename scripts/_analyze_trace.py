#!/usr/bin/env python3
"""Quick analysis of deflection trace results."""
import json, sys, glob

# Find latest trace file
files = sorted(glob.glob("results/deflection_11_trace_v4_*.json"))
if not files:
    print("No trace files found")
    sys.exit(1)
path = files[-1]
print(f"Analyzing: {path}\n")

with open(path, "r") as f:
    data = json.load(f)

for r in data["results"]:
    if not r["passed"]:
        t = r.get("trace", {})
        tag = "DEFLECTION" if r["is_deflection"] else "FAIL"
        print(f"{'='*70}")
        print(f"TEST #{r['id']}: {r['question']}")
        print(f"Status: {tag}")
        print(f"Response: {r['response'][:250]}")
        print(f"Intent: {r['intent']}  Action: {r['action']}  State: {r['state']}")
        print(f"Template: {t.get('selected_template_key', '?')}")
        print(f"FactKeys: {t.get('fact_keys', [])}")
        print(f"ReasonCodes: {t.get('reason_codes', [])}")
        print(f"VerifierVerdict: {t.get('factual_verifier_verdict', '?')}")
        print(f"VerifierChanged: {t.get('factual_verifier_changed', False)}")
        ve = t.get("validation_events", [])
        if ve:
            print(f"ValidationEvents: {ve}")

        qi = t.get("question_instruction", "")
        print(f"QuestionInstruction: {qi[:300] if qi else '(empty)'}")

        sgr = t.get("state_gated_rules", "")
        if sgr:
            print(f"StateGatedRules (first 400):")
            print(sgr[:400])

        rf = t.get("retrieved_facts", "")
        print(f"\nRetrievedFacts ({len(rf)} chars):")
        print(rf[:600] if rf else "(empty)")

        print(f"\nTotalPrompts: {t.get('total_prompts_in_turn', 0)}")

        prompt = t.get("last_prompt", "")
        if prompt:
            print(f"\nPrompt tail (last 1000 chars):")
            print(prompt[-1000:])
        print()
