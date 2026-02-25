"""
Manual E2E dialog runner for pre/post fix comparison.
Tests cover all areas addressed by the 5 fixes in the plan.
Usage:
    python -m scripts.manual_e2e_dialogs --label pre
    python -m scripts.manual_e2e_dialogs --label post
"""
import argparse
import json
import sys
import io
from datetime import datetime
from pathlib import Path
from contextlib import redirect_stdout

# ---------------------------------------------------------------------------
# Dialog scenarios
# Each scenario is a list of user messages sent sequentially.
# Named after the main thing being tested.
# ---------------------------------------------------------------------------
SCENARIOS = [
    {
        "id": "D01",
        "name": "Price question - Mini (Fix3: pricing signal → tariff, no disambig)",
        "messages": [
            "Здравствуйте",
            "Хочу автоматизировать небольшой магазин продуктов",
            "Сколько стоит Mini?",
        ],
    },
    {
        "id": "D02",
        "name": "What-includes Mini (Fix3: no signal, 1 family → SHOULD disambig)",
        "messages": [
            "Здравствуйте",
            "Интересует ваше решение для магазина",
            "Что включает Mini?",
        ],
    },
    {
        "id": "D03",
        "name": "Tell me about Pro - disambiguation then Standard (Fix4: per-family)",
        "messages": [
            "Здравствуйте",
            "Расскажите про Pro",          # → disambiguation
            "1",                           # → выбор 'Тариф Pro'
            "А что по Standard?",          # → НЕ должно быть повторного disambiguation
        ],
    },
    {
        "id": "D04",
        "name": "Lite vs Standard comparison (Fix3: 2 families → tariff, no disambig)",
        "messages": [
            "Здравствуйте",
            "Что рациональнее взять: Lite или Standard?",
        ],
    },
    {
        "id": "D05",
        "name": "Standard vs Pro difference (Fix3: 2 families → tariff, no disambig)",
        "messages": [
            "Здравствуйте",
            "У меня несколько точек, интересно",
            "Чем Standard отличается от Pro?",
        ],
    },
    {
        "id": "D06",
        "name": "Equipment question (Fix3: equipment signal → kit, no disambig)",
        "messages": [
            "Здравствуйте",
            "Что за оборудование входит в комплект Standard?",
        ],
    },
    {
        "id": "D07",
        "name": "Disambiguation + normal bot turn + old disambig NOT applied (Fix5)",
        "messages": [
            "Здравствуйте",
            "Расскажите про Lite",           # → disambiguation
            "2",                             # → выбрал опцию 2
            "Отлично, а теперь про ваши услуги поддержки",   # нормальный ход, старый disambig не применяется
            "Что входит в Standard?",        # ещё один вопрос
        ],
    },
    {
        "id": "D08",
        "name": "НЕ ПУТАТЬ leak check (Fix2: stripped from answer to client)",
        "messages": [
            "Здравствуйте",
            "Расскажите о тарифе Pro",
            "1",   # выбрать тариф если disambig
            "Какие ограничения у Pro?",
        ],
    },
    {
        "id": "D09",
        "name": "Full-content check (Fix1: 25000 chars, no truncation)",
        "messages": [
            "Здравствуйте",
            "У меня магазин, интересует автоматизация",
            "Расскажите подробно обо всех тарифах",
        ],
    },
    {
        "id": "D10",
        "name": "Equipment monoblock + price question (both signals → None → disambig)",
        "messages": [
            "Здравствуйте",
            "Цена Pro и комплект Pro — в чём разница?",  # both signals → None → disambig
        ],
    },
]


def run_dialog(scenario: dict, bot) -> dict:
    """Run a single dialog scenario and capture results."""
    results = []
    bot.reset()

    for i, msg in enumerate(scenario["messages"]):
        result = bot.process(msg)
        entry = {
            "turn": i + 1,
            "user": msg,
            "bot": result["response"],
            "state": result.get("state", ""),
            "action": result.get("action", ""),
            "spin_phase": result.get("spin_phase", ""),
        }
        # Capture disambiguation info from logs if available
        results.append(entry)

        if result.get("is_final"):
            break

    return {
        "id": scenario["id"],
        "name": scenario["name"],
        "turns": results,
    }


def check_issues(dialog: dict) -> list:
    """Check for known problem patterns in dialog output."""
    issues = []
    for turn in dialog["turns"]:
        bot_text = turn["bot"]

        # Check 1: НЕ ПУТАТЬ leak (Fix 2)
        if "НЕ ПУТАТЬ" in bot_text or "НЕ ПУТАЙ" in bot_text:
            issues.append(f"[T{turn['turn']}] НЕ ПУТАТЬ leak в ответе: {bot_text[:100]}")

        # Check 2: Truncation indicator (Fix 1)
        if "..." in bot_text and len(bot_text) > 200:
            # Could be truncated KB content leaked through
            pass

        # Check 3: Disambiguation prompt in message about pricing
        if "ответьте номером" in bot_text.lower() or "уточните, пожалуйста" in bot_text.lower():
            turn["has_disambiguation"] = True
        else:
            turn["has_disambiguation"] = False

    return issues


def print_dialog(dialog: dict, label: str):
    lines = []
    lines.append(f"\n{'='*70}")
    lines.append(f"[{label}] {dialog['id']}: {dialog['name']}")
    lines.append("="*70)
    for turn in dialog["turns"]:
        disambig_mark = " [DISAMBIG]" if turn.get("has_disambiguation") else ""
        lines.append(f"  U: {turn['user']}")
        lines.append(f"  B: {turn['bot'][:300]}{'...' if len(turn['bot']) > 300 else ''}{disambig_mark}")
        lines.append(f"     [{turn['state']}] {turn['action']} {turn['spin_phase']}")
        lines.append("")
    issues = check_issues(dialog)
    if issues:
        lines.append("  ⚠️  ISSUES:")
        for issue in issues:
            lines.append(f"     {issue}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="pre", choices=["pre", "post"])
    args = parser.parse_args()

    # Import bot
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.bot import SalesBot
    from src.llm import OllamaLLM
    from src.feature_flags import flags

    llm = OllamaLLM()
    bot = SalesBot(llm, flow_name="autonomous")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = Path(__file__).parent.parent / "results" / f"manual_e2e_{args.label}_{timestamp}.json"
    output_file.parent.mkdir(exist_ok=True)

    all_results = []
    summary_lines = []
    summary_lines.append(f"\n{'#'*70}")
    summary_lines.append(f"# E2E Manual Dialogs — {args.label.upper()} FIX — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    summary_lines.append(f"# response_fact_disambiguation: {flags.is_enabled('response_fact_disambiguation')}")
    summary_lines.append(f"# max_kb_chars from settings: (see logs)")
    summary_lines.append(f"{'#'*70}")
    print("\n".join(summary_lines))

    for scenario in SCENARIOS:
        print(f"\nRunning {scenario['id']}: {scenario['name']}")
        dialog = run_dialog(scenario, bot)
        check_issues(dialog)  # adds has_disambiguation field
        output = print_dialog(dialog, args.label)
        print(output)
        all_results.append(dialog)

    # Save JSON
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "label": args.label,
                "timestamp": timestamp,
                "scenarios": all_results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\n✅ Results saved to: {output_file}")

    # Print disambiguation summary
    print(f"\n{'='*70}")
    print("DISAMBIGUATION SUMMARY")
    print("="*70)
    for dialog in all_results:
        disambig_turns = [t for t in dialog["turns"] if t.get("has_disambiguation")]
        expected_disambig = dialog["id"] in ("D02", "D10")
        unexpected_disambig = len(disambig_turns) > 0 and not expected_disambig
        no_expected_disambig = len(disambig_turns) == 0 and expected_disambig

        status = "OK"
        if unexpected_disambig:
            status = f"⚠️  UNEXPECTED DISAMBIG at turns {[t['turn'] for t in disambig_turns]}"
        if no_expected_disambig:
            status = "⚠️  MISSING EXPECTED DISAMBIG"

        print(f"  {dialog['id']}: {status}")

    # НЕ ПУТАТЬ check
    print(f"\n{'='*70}")
    print("НЕ ПУТАТЬ LEAK CHECK")
    print("="*70)
    for dialog in all_results:
        leaks = []
        for turn in dialog["turns"]:
            if "НЕ ПУТАТЬ" in turn["bot"] or "НЕ ПУТАЙ" in turn["bot"]:
                leaks.append(turn["turn"])
        status = f"⚠️  LEAK at turns {leaks}" if leaks else "OK"
        print(f"  {dialog['id']}: {status}")


if __name__ == "__main__":
    main()
