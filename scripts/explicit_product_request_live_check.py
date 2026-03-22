#!/usr/bin/env python3
"""
Focused live E2E check for explicit named product requests in autonomous flow.

Runs three short scenarios through the real SalesBot + Ollama + TEI pipeline and
captures whether the bot:
1. recognizes and acknowledges the concrete named product first,
2. avoids drifting into generic greeting/name-asking behavior,
3. avoids double self-introduction in the first reply.
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
    "я айбота",
    "консультант wipon",
    "ваш консультант wipon",
    "ваш персональный консультант wipon",
)

NAME_ASK_MARKERS = (
    "как к вам обращаться",
    "как к вам лучше обращаться",
    "как вас зовут",
    "как могу к вам обращаться",
)

PRODUCT_MARKERS = (
    "standard+",
    "standard",
    "lite",
    "mini",
    "pro",
    "комплект",
)


SCENARIOS = [
    {
        "id": "P1_bundle_standard_plus_city",
        "messages": [
            'Здравствуйте! Мне нужен Комплект Standard+ в Алматы.',
        ],
        "expected_product_markers": ["standard+", "комплект"],
    },
    {
        "id": "P2_tariff_lite_direct",
        "messages": [
            'Здравствуйте, хочу тариф Lite для одного магазина.',
        ],
        "expected_product_markers": ["lite"],
    },
    {
        "id": "P3_mix_greeting_and_named_product",
        "messages": [
            'Добрый день. Беру Standard для магазина у дома, что дальше?',
        ],
        "expected_product_markers": ["standard"],
        "expected_next_step_markers": ["следующ", "оформ", "подключ", "счет", "счёт", "связ"],
    },
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip()).lower()


def _count_intro_mentions(text: str) -> int:
    low = _normalize(text)
    return low.count("айбота")


def _has_name_ask(text: str) -> bool:
    low = _normalize(text)
    return any(marker in low for marker in NAME_ASK_MARKERS)


def _mentions_expected_product(text: str, expected_product_markers: list[str]) -> bool:
    low = _normalize(text)
    return any(marker in low for marker in expected_product_markers)


def _mentions_next_step(text: str, expected_next_step_markers: list[str]) -> bool:
    low = _normalize(text)
    if not expected_next_step_markers:
        return True
    return any(marker in low for marker in expected_next_step_markers)


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
        dialog = []
        violations = []

        for turn_idx, user_msg in enumerate(scenario["messages"], start=1):
            print(f"U{turn_idx}: {user_msg}", flush=True)
            result = bot.process(user_msg)
            response = result.get("response", "")
            meta = getattr(bot.generator, "_last_postprocess_meta", {}) or {}
            trace = meta.get("postprocess_trace") or []
            intro_mentions = _count_intro_mentions(response)
            asks_name = _has_name_ask(response)
            product_ack = _mentions_expected_product(response, scenario["expected_product_markers"])
            next_step_ack = _mentions_next_step(response, scenario.get("expected_next_step_markers", []))
            repeat_intro_same_message = intro_mentions >= 2

            if asks_name:
                violations.append({"turn": turn_idx, "type": "asked_name", "response": response})
            if not product_ack:
                violations.append({"turn": turn_idx, "type": "missed_named_product", "response": response})
            if not next_step_ack:
                violations.append({"turn": turn_idx, "type": "missed_next_step_guidance", "response": response})
            if repeat_intro_same_message:
                violations.append({"turn": turn_idx, "type": "double_self_intro_same_message", "response": response})

            turn_payload = {
                "turn": turn_idx,
                "user": user_msg,
                "bot": response,
                "state": result.get("state"),
                "action": result.get("action"),
                "intent": result.get("intent"),
                "product_ack": product_ack,
                "next_step_ack": next_step_ack,
                "asks_name": asks_name,
                "intro_mentions": intro_mentions,
                "postprocess_last_mutation_rule": meta.get("postprocess_last_mutation_rule"),
                "postprocess_trace_rules": [item.get("rule_id") for item in trace],
            }
            dialog.append(turn_payload)

            print(f"B{turn_idx}: {response}", flush=True)
            print(
                "   "
                + json.dumps(
                    {
                        "intent": turn_payload["intent"],
                        "state": turn_payload["state"],
                        "action": turn_payload["action"],
                        "product_ack": product_ack,
                        "next_step_ack": next_step_ack,
                        "asks_name": asks_name,
                        "intro_mentions": intro_mentions,
                        "postprocess_last_mutation_rule": turn_payload["postprocess_last_mutation_rule"],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

        scenario_result = {
            "id": scenario["id"],
            "passed": not violations,
            "violations": violations,
            "turns": dialog,
        }
        results.append(scenario_result)
        print(f"RESULT {scenario['id']}: {'PASS' if scenario_result['passed'] else 'FAIL'}", flush=True)

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
    out_path = out_dir / "explicit_product_request_live.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nSUMMARY", flush=True)
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2), flush=True)
    print(f"Saved: {out_path}", flush=True)


if __name__ == "__main__":
    main()
