"""
Focused E2E runner for client-name addressing behavior.

Runs the same 4 dialogs before/after a fix and measures how often the bot
addresses the client by name.

Usage:
    python -m scripts.name_addressing_e2e --label pre
    python -m scripts.name_addressing_e2e --label post
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List


SCENARIOS = [
    {
        "id": "N01",
        "name": "Имя названо рано, дальше factual Q&A",
        "client_name": "Алия",
        "messages": [
            "Здравствуйте, меня зовут Алия. У меня магазин у дома.",
            "Сколько стоит Mini?",
            "А что входит в Mini?",
            "А техподдержка как работает?",
        ],
    },
    {
        "id": "N02",
        "name": "Полное имя + несколько уточнений подряд",
        "client_name": "Марат",
        "messages": [
            "Добрый день, я Марат Сейткали, у нас две торговые точки.",
            "Подойдёт ли Standard?",
            "А если точек станет пять?",
            "Что по складу внутри?",
        ],
    },
    {
        "id": "N03",
        "name": "Имя после первого вопроса",
        "client_name": "Айгерим",
        "messages": [
            "Здравствуйте, интересует автоматизация кофейни.",
            "Меня Айгерим зовут. Что у вас по интеграции с Kaspi?",
            "А по цене Lite сколько?",
            "Можно ли без звонка пока просто здесь узнать?",
        ],
    },
    {
        "id": "N04",
        "name": "Имя и длинный discovery/closing хвост",
        "client_name": "Дмитрий",
        "messages": [
            "Привет, я Дмитрий. Открываю небольшой магазин электроники.",
            "Что лучше взять на старт?",
            "А если потом подключу склад?",
            "Есть тестовый период?",
        ],
    },
]


def _name_markers(name: str) -> List[str]:
    cleaned = " ".join(str(name or "").strip().split())
    if not cleaned:
        return []
    parts = [p for p in cleaned.split() if p]
    markers = [cleaned.lower()]
    first = parts[0].lower()
    if first not in markers:
        markers.append(first)
    return markers


def _contains_name(text: str, name: str) -> bool:
    low = str(text or "").lower()
    for marker in _name_markers(name):
        if " " in marker:
            pattern = r"(?<!\w)" + re.escape(marker).replace(r"\ ", r"\s+") + r"(?!\w)"
        else:
            pattern = r"(?<!\w)" + re.escape(marker) + r"(?!\w)"
        if re.search(pattern, low):
            return True
    return False


def _starts_with_name(text: str, name: str) -> bool:
    low = str(text or "").strip().lower()
    for marker in _name_markers(name):
        patterns = [
            r"^" + re.escape(marker) + r"[,.!?:\s]",
            r"^(ну\s+)?"+ re.escape(marker) + r"[,.!?:\s]",
            r"^(смотрите,\s+)?" + re.escape(marker) + r"[,.!?:\s]",
        ]
        if any(re.search(pattern, low) for pattern in patterns):
            return True
    return False


def _max_allowed_mentions(bot_turns: int) -> int:
    return max(1, math.ceil(bot_turns / 4))


def run_dialog(scenario: Dict, bot) -> Dict:
    bot.reset()
    turns = []
    name = scenario["client_name"]

    for idx, message in enumerate(scenario["messages"], start=1):
        result = bot.process(message)
        response = result["response"]
        turns.append(
            {
                "turn": idx,
                "user": message,
                "bot": response,
                "contains_name": _contains_name(response, name),
                "starts_with_name": _starts_with_name(response, name),
                "state": result.get("state", ""),
                "action": result.get("action", ""),
                "spin_phase": result.get("spin_phase", ""),
            }
        )
        if result.get("is_final"):
            break

    name_turns = [turn["turn"] for turn in turns if turn["contains_name"]]
    start_turns = [turn["turn"] for turn in turns if turn["starts_with_name"]]
    allowed = _max_allowed_mentions(len(turns))

    return {
        "id": scenario["id"],
        "name": scenario["name"],
        "client_name": name,
        "turns": turns,
        "metrics": {
            "bot_turns": len(turns),
            "name_mentions": len(name_turns),
            "name_turns": name_turns,
            "starts_with_name_turns": start_turns,
            "max_allowed_mentions": allowed,
            "passes_frequency": len(name_turns) <= allowed,
            "passes_opening_rule": len(start_turns) == 0,
        },
    }


def render_dialog(dialog: Dict, label: str) -> str:
    lines = []
    metrics = dialog["metrics"]
    status = "PASS" if metrics["passes_frequency"] and metrics["passes_opening_rule"] else "FAIL"
    lines.append(f"\n{'=' * 72}")
    lines.append(f"[{label}] {dialog['id']} {status} — {dialog['name']} ({dialog['client_name']})")
    lines.append(
        "mentions="
        f"{metrics['name_mentions']}/{metrics['bot_turns']} "
        f"(allowed <= {metrics['max_allowed_mentions']}), "
        f"starts={metrics['starts_with_name_turns'] or '[]'}"
    )
    lines.append("=" * 72)
    for turn in dialog["turns"]:
        marks = []
        if turn["contains_name"]:
            marks.append("NAME")
        if turn["starts_with_name"]:
            marks.append("START")
        suffix = f" [{' '.join(marks)}]" if marks else ""
        lines.append(f"U{turn['turn']}: {turn['user']}")
        lines.append(f"B{turn['turn']}: {turn['bot']}{suffix}")
        lines.append(f"    [{turn['state']}] {turn['action']} {turn['spin_phase']}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="pre", choices=["pre", "post"])
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.bot import SalesBot, setup_autonomous_pipeline
    from src.llm import OllamaLLM

    setup_autonomous_pipeline()
    bot = SalesBot(OllamaLLM(), flow_name="autonomous")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(__file__).parent.parent / "results"
    out_dir.mkdir(exist_ok=True)
    output_file = out_dir / f"name_addressing_e2e_{args.label}_{timestamp}.json"

    results = []
    print(f"Running focused name-addressing E2E: label={args.label}, scenarios={len(SCENARIOS)}")
    for scenario in SCENARIOS:
        print(f"\nRunning {scenario['id']}: {scenario['name']}")
        dialog = run_dialog(scenario, bot)
        print(render_dialog(dialog, args.label))
        results.append(dialog)

    summary = {
        "label": args.label,
        "timestamp": timestamp,
        "scenarios": results,
        "aggregate": {
            "dialogs": len(results),
            "failed_frequency": [r["id"] for r in results if not r["metrics"]["passes_frequency"]],
            "failed_opening_rule": [r["id"] for r in results if not r["metrics"]["passes_opening_rule"]],
            "total_name_mentions": sum(r["metrics"]["name_mentions"] for r in results),
            "total_bot_turns": sum(r["metrics"]["bot_turns"] for r in results),
        },
    }

    with output_file.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)

    print(f"\nSaved results to {output_file}")
    print("\nSUMMARY")
    print(json.dumps(summary["aggregate"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
