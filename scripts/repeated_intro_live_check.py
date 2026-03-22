#!/usr/bin/env python3
"""
Focused live E2E check for repeated bot self-introduction in autonomous flow.

Runs three short scenarios through the real SalesBot + Ollama + TEI pipeline
and captures whether repeated self-intro leaked to the client on non-first bot
turns. Also records generator postprocess metadata for the suppression rule.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path

from src.bot import SalesBot, setup_autonomous_pipeline
from src.llm import OllamaLLM


INTRO_MARKERS = (
    "меня зовут айбота",
    "ваш консультант wipon",
    "ваш персональный консультант wipon",
)


SCENARIOS = [
    {
        "id": "S1_fact_followup_like_screenshot",
        "messages": [
            "Здравствуйте! Мне нужен комплект Стандарт+ в Алматы.",
            "Он подходит для кондитерского магазина?",
        ],
    },
    {
        "id": "S2_pure_repeat_greeting",
        "messages": [
            "Здравствуйте",
            "Здравствуйте",
        ],
    },
    {
        "id": "S3_greeting_prefixed_followup",
        "messages": [
            "Здравствуйте",
            "Здравствуйте ещё раз. Сколько стоит Standard+ для магазина в Алматы?",
        ],
    },
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip()).lower()


def _has_intro(text: str) -> bool:
    normalized = _normalize(text)
    return any(marker in normalized for marker in INTRO_MARKERS)


def run() -> dict:
    setup_autonomous_pipeline()
    llm = OllamaLLM()
    if hasattr(llm, "reset_circuit_breaker"):
        llm.reset_circuit_breaker()

    started = time.time()
    results = []

    for scenario in SCENARIOS:
        print(f"\n=== {scenario['id']} ===", flush=True)
        bot = SalesBot(llm, flow_name="autonomous", enable_tracing=True)
        intro_seen_before = False
        dialog = []
        violations = []

        for turn_idx, user_msg in enumerate(scenario["messages"], start=1):
            print(f"U{turn_idx}: {user_msg}", flush=True)
            result = bot.process(user_msg)
            response = result.get("response", "")
            meta = getattr(bot.generator, "_last_postprocess_meta", {}) or {}
            trace = meta.get("postprocess_trace") or []
            suppress_entry = next(
                (item for item in trace if item.get("rule_id") == "suppress_repeated_self_intro"),
                {},
            )
            intro_now = _has_intro(response)
            repeated_intro_violation = intro_seen_before and intro_now
            if repeated_intro_violation:
                violations.append({"turn": turn_idx, "response": response})

            turn_payload = {
                "turn": turn_idx,
                "user": user_msg,
                "bot": response,
                "state": result.get("state"),
                "action": result.get("action"),
                "intro_seen_before": intro_seen_before,
                "intro_in_response": intro_now,
                "repeat_intro_violation": repeated_intro_violation,
                "postprocess_last_mutation_rule": meta.get("postprocess_last_mutation_rule"),
                "suppression_changed": bool(suppress_entry.get("changed", False)),
                "suppression_enabled": bool(suppress_entry.get("enabled", False)),
            }
            dialog.append(turn_payload)
            print(f"B{turn_idx}: {response}", flush=True)
            print(
                "   "
                + json.dumps(
                    {
                        "state": turn_payload["state"],
                        "action": turn_payload["action"],
                        "intro_in_response": intro_now,
                        "intro_seen_before": turn_payload["intro_seen_before"],
                        "repeat_intro_violation": repeated_intro_violation,
                        "postprocess_last_mutation_rule": turn_payload["postprocess_last_mutation_rule"],
                        "suppression_changed": turn_payload["suppression_changed"],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            intro_seen_before = intro_seen_before or intro_now

        scenario_result = {
            "id": scenario["id"],
            "passed": not violations,
            "violations": violations,
            "turns": dialog,
        }
        results.append(scenario_result)
        print(
            f"RESULT {scenario['id']}: {'PASS' if scenario_result['passed'] else 'FAIL'}",
            flush=True,
        )

    payload = {
        "timestamp": datetime.now().isoformat(),
        "elapsed_sec": round(time.time() - started, 2),
        "scenarios": results,
        "summary": {
            "total": len(results),
            "passed": sum(1 for result in results if result["passed"]),
            "failed": [result["id"] for result in results if not result["passed"]],
        },
    }
    return payload


def main() -> None:
    payload = run()
    out_dir = Path("results")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "repeated_intro_live.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nSUMMARY", flush=True)
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2), flush=True)
    print(f"Saved: {out_path}", flush=True)


if __name__ == "__main__":
    main()
