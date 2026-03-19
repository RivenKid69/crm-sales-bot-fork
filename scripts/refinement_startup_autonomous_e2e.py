"""
Focused autonomous E2E for startup refinement layers.

Validates that:
- first_contact refinement keeps early cautious leads out of objection flow
- greeting_context refinement normalizes greeting-time technical/reference intents

Run inside the full Docker network with live Ollama + TEI services.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List


sys.path.insert(0, str(Path(__file__).parent.parent))


SCENARIOS: List[Dict[str, Any]] = [
    {
        "id": "first_contact_refinement",
        "description": "Early cautious lead should stay consultative, not objection-driven.",
        "messages": [
            "Слушайте, мне вас коллега посоветовал, но я пока не уверен, хочу понять, что у вас за система",
            "У нас три магазина одежды, хотим навести порядок с остатками и продажами",
        ],
    },
    {
        "id": "greeting_context_technical",
        "description": "Greeting-time technical complaint should normalize into discovery instead of support/escalation.",
        "messages": [
            "Синхронизация между точками постоянно ломается",
            "Из-за этого я не вижу нормальные остатки и продажи по магазинам",
        ],
    },
    {
        "id": "greeting_context_references",
        "description": "Greeting-time reference request should stay sales-oriented, not jump straight to references flow.",
        "messages": [
            "Кто ваши клиенты, кому вы уже внедряли систему?",
            "У нас две аптеки, хочу понять, подойдёт ли решение под нас",
        ],
    },
]


def _trim(value: Any, limit: int = 260) -> str:
    text = str(value)
    return text if len(text) <= limit else text[:limit] + "..."


def inspect_classification(bot, message: str) -> Dict[str, Any]:
    context = bot._get_classification_context()
    result = bot.classifier.classify(message, context)
    return {
        "intent": result.get("intent"),
        "original_intent": result.get("original_intent"),
        "refinement_reason": result.get("refinement_reason"),
        "refinement_chain": result.get("refinement_chain", []),
        "confidence": result.get("confidence"),
        "secondary_signals": result.get("secondary_signals", []),
    }


def run_scenario(bot, scenario: Dict[str, Any]) -> Dict[str, Any]:
    bot.reset()
    turns: List[Dict[str, Any]] = []

    for turn_no, message in enumerate(scenario["messages"], start=1):
        classification = inspect_classification(bot, message)

        start = time.time()
        result = bot.process(message)
        elapsed_ms = (time.time() - start) * 1000

        turns.append(
            {
                "turn": turn_no,
                "user": message,
                "classification": classification,
                "result": {
                    "intent": result.get("intent"),
                    "action": result.get("action"),
                    "state": result.get("state"),
                    "confidence": result.get("confidence"),
                    "reason_codes": result.get("reason_codes", []),
                    "response": result.get("response"),
                },
                "elapsed_ms": round(elapsed_ms, 1),
            }
        )

        if result.get("is_final"):
            break

    return {
        "id": scenario["id"],
        "description": scenario["description"],
        "turns": turns,
    }


def print_report(report: Dict[str, Any]) -> None:
    print("=" * 88)
    print(report["id"])
    print(report["description"])
    print("=" * 88)

    for turn in report["turns"]:
        cls = turn["classification"]
        result = turn["result"]
        print(f"[T{turn['turn']}] user={turn['user']}")
        print(
            "  classify:"
            f" intent={cls['intent']}"
            f" original={cls['original_intent']}"
            f" chain={cls['refinement_chain']}"
            f" reason={cls['refinement_reason']}"
            f" conf={cls['confidence']}"
        )
        print(
            "  process: "
            f"intent={result['intent']} action={result['action']} state={result['state']} "
            f"reason_codes={result['reason_codes']} elapsed_ms={turn['elapsed_ms']}"
        )
        print(f"  response: {_trim(result['response'])}")
        print()


def main() -> None:
    from src.bot import SalesBot, setup_autonomous_pipeline
    from src.llm import OllamaLLM

    print("Initializing autonomous pipeline...")
    init_start = time.time()
    llm = OllamaLLM()
    setup_autonomous_pipeline()
    bot = SalesBot(llm, flow_name="autonomous", enable_tracing=True)
    print(f"Ready in {time.time() - init_start:.1f}s")
    print()

    reports = [run_scenario(bot, scenario) for scenario in SCENARIOS]

    for report in reports:
        print_report(report)

    print("JSON_SUMMARY_START")
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    print("JSON_SUMMARY_END")


if __name__ == "__main__":
    main()
