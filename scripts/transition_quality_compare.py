"""
Transition Quality Comparison — before vs after reasoning-first + required fix.

3 most illustrative scenarios, run N times each label.
Captures AutonomousDecision.reasoning to show whether CoT actually happens.

Usage:
    python -m scripts.transition_quality_compare --label pre  --runs 3
    python -m scripts.transition_quality_compare --label post --runs 3
"""

import json
import sys
import argparse
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# 3 most illustrative scenarios (selected from original 5)
# ---------------------------------------------------------------------------

SCENARIOS = [
    {
        "id": "T01",
        "name": "Discovery → Qual: бизнес + боль + команда — должен перейти",
        "description": (
            "Client gives: business type, 3 locations, pain point (Excel), team size (10)."
            " Bot should transition to qualification by turn 4."
        ),
        "expected_transition_by": 4,  # None = expect NO transition
        "messages": [
            "Здравствуйте",
            "У меня продуктовый магазин, 3 точки в Алматы. Основная проблема — не понимаю остатки по товарам, всё вручную в Excel.",
            "Сколько сотрудников обычно нужно для работы с вашей системой?",
            "У нас 8 кассиров и 2 администратора",
        ],
    },
    {
        "id": "T03",
        "name": "Qual → Presentation: бюджет + сроки названы",
        "description": (
            "Client gives pain point, then explicit budget + timeline."
            " Bot should transition to presentation by turn 5."
        ),
        "expected_transition_by": 5,
        "messages": [
            "Здравствуйте",
            "Магазин косметики, 1 точка, Нур-Султан",
            "Главная проблема — нет учёта возвратов и нет лояльности для клиентов",
            "Бюджет около 20 000 в месяц, хотим подключить в течение месяца",
            "Что именно можете предложить для нашего случая?",
        ],
    },
    {
        "id": "T04",
        "name": "Obj → Closing: клиент смягчается после отработки возражения",
        "description": (
            "Full chain: price heard → objection → soften → 'давайте Standard'."
            " Should reach closing by turn 6."
        ),
        "expected_transition_by": 6,
        "messages": [
            "Здравствуйте",
            "Ресторан + доставка, 2 точки",
            "Сколько стоит Pro?",
            "500 000 — это слишком много для нас",
            "Хорошо, а если без модуля кадрового учёта? Нам это не нужно",
            "Понял, давайте тогда Standard. Как оформить?",
        ],
    },
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_decision_history(bot) -> list:
    try:
        source = bot._orchestrator.get_source("AutonomousDecisionSource")
        if source and hasattr(source, "decision_history"):
            return list(source.decision_history)
    except Exception:
        pass
    return []


def run_scenario(scenario: dict, bot) -> dict:
    bot.reset()
    turns = []
    prev_history_len = 0

    for i, msg in enumerate(scenario["messages"]):
        result = bot.process(msg)
        turn_num = i + 1

        full_history = get_decision_history(bot)
        new_records = full_history[prev_history_len:]
        prev_history_len = len(full_history)

        decision_info = None
        if new_records:
            rec = new_records[-1]
            decision_info = {
                "should_transition": getattr(rec, "should_transition", None),
                "next_state": getattr(rec, "next_state", None),
                "reasoning": getattr(rec, "reasoning", ""),
                "state_before": getattr(rec, "state", None),
            }

        turns.append({
            "turn": turn_num,
            "user": msg,
            "bot": result["response"][:300],
            "state_after": result.get("state", ""),
            "spin_phase": result.get("spin_phase", ""),
            "decision": decision_info,
        })

        if result.get("is_final"):
            break

    expected_by = scenario.get("expected_transition_by")
    transitioned_at = None
    for t in turns:
        d = t.get("decision")
        if d and d.get("should_transition"):
            transitioned_at = t["turn"]
            break

    if expected_by is None:
        premature = transitioned_at is not None and transitioned_at <= 3
        verdict = "PASS" if not premature else "FAIL (premature)"
    else:
        if transitioned_at is None:
            verdict = "FAIL (no transition)"
        elif transitioned_at <= expected_by:
            verdict = "PASS"
        else:
            verdict = f"LATE (turn {transitioned_at}, expected ≤{expected_by})"

    return {
        "id": scenario["id"],
        "name": scenario["name"],
        "turns": turns,
        "transitioned_at": transitioned_at,
        "expected_transition_by": expected_by,
        "verdict": verdict,
    }


# ---------------------------------------------------------------------------
# Per-run report
# ---------------------------------------------------------------------------

def print_run(run_idx: int, results: list, label: str):
    passed = sum(1 for r in results if r["verdict"] == "PASS")
    print(f"\n── Run {run_idx} [{label}] {passed}/{len(results)} PASS ──")

    for r in results:
        icon = "✅" if r["verdict"] == "PASS" else ("⚠️" if "LATE" in r["verdict"] else "❌")
        print(f"  {icon} {r['id']} | verdict={r['verdict']} | transitioned_at={r['transitioned_at']}")

        for t in r["turns"]:
            d = t.get("decision")
            if not d:
                continue
            trans_flag = "→ TRANSIT" if d.get("should_transition") else "  stay   "
            reasoning = d.get("reasoning", "")
            r_preview = f" | reasoning: «{reasoning[:100]}»" if reasoning else " | reasoning: (empty)"
            print(
                f"    T{t['turn']} [{t['state_after']}] {trans_flag}"
                f" → {d.get('next_state')}"
                f"{r_preview}"
            )


# ---------------------------------------------------------------------------
# Aggregate summary across multiple runs
# ---------------------------------------------------------------------------

def print_aggregate(all_runs: list, label: str):
    n_runs = len(all_runs)
    print(f"\n{'='*70}")
    print(f"AGGREGATE [{label.upper()}] — {n_runs} runs × {len(SCENARIOS)} scenarios")
    print(f"{'='*70}")

    by_scenario: dict = {}
    for run in all_runs:
        for r in run:
            sid = r["id"]
            by_scenario.setdefault(sid, {"pass": 0, "fail": 0, "late": 0, "reasoning_samples": []})
            v = r["verdict"]
            if v == "PASS":
                by_scenario[sid]["pass"] += 1
            elif "LATE" in v:
                by_scenario[sid]["late"] += 1
            else:
                by_scenario[sid]["fail"] += 1

            # Collect non-empty reasoning samples
            for t in r["turns"]:
                d = t.get("decision") or {}
                if d.get("reasoning"):
                    by_scenario[sid]["reasoning_samples"].append(d["reasoning"])

    total_pass = 0
    total_runs = 0
    for sid, stats in by_scenario.items():
        p = stats["pass"]
        f = stats["fail"]
        la = stats["late"]
        total_pass += p
        total_runs += n_runs
        samples = stats["reasoning_samples"]
        has_reasoning = len(samples) > 0
        reasoning_note = f"reasoning filled {len(samples)}/{n_runs} runs" if has_reasoning else "reasoning ALWAYS EMPTY"

        icon = "✅" if f == 0 and la == 0 else ("⚠️" if la > 0 or (f < n_runs) else "❌")
        print(f"  {icon} {sid}: {p}/{n_runs} PASS, {la} LATE, {f} FAIL | {reasoning_note}")
        if samples:
            print(f"       Sample reasoning: «{samples[0][:120]}»")

    print(f"\n  TOTAL: {total_pass}/{total_runs} PASS across all runs")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="pre", choices=["pre", "post", "pre_orig"])
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.bot import SalesBot, setup_autonomous_pipeline
    from src.llm import OllamaLLM

    setup_autonomous_pipeline()

    llm = OllamaLLM()
    bot = SalesBot(llm, flow_name="autonomous")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    all_runs = []

    for run_idx in range(1, args.runs + 1):
        print(f"\nRun {run_idx}/{args.runs} [{args.label}] ...", flush=True)
        run_results = []
        for scenario in SCENARIOS:
            print(f"  {scenario['id']} ...", end="", flush=True)
            r = run_scenario(scenario, bot)
            run_results.append(r)
            icon = "✅" if r["verdict"] == "PASS" else "❌"
            print(f" {icon} {r['verdict']}", flush=True)
        all_runs.append(run_results)
        print_run(run_idx, run_results, args.label)

    print_aggregate(all_runs, args.label)

    # Save JSON
    results_dir = Path(__file__).parent.parent / "results"
    results_dir.mkdir(exist_ok=True)
    path = results_dir / f"tq_{args.label}_{ts}.json"
    path.write_text(
        json.dumps(
            {"label": args.label, "runs": args.runs, "timestamp": ts, "all_runs": all_runs},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"JSON: {path}")

    total_pass = sum(
        1 for run in all_runs for r in run if r["verdict"] == "PASS"
    )
    total = args.runs * len(SCENARIOS)
    sys.exit(0 if total_pass == total else 1)


if __name__ == "__main__":
    main()
