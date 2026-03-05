"""
Graduation Criteria + Temperature Compare.

5 scenarios targeting exactly the two changed mechanisms:
  - Change #3: temperature 0.1 → 0.05 (determinism of should_transition)
  - Change #4: explicit SPIN graduation criteria in decision prompt

Scenario design:
  S01 — discovery: business_type + pain_point → MUST transition (graduation #1 fires)
  S02 — discovery: business_type only, no pain → MUST stay    (graduation #1 silent)
  S03 — qualification: explicit budget stated  → MUST transition (graduation #2 fires)
  S04 — qualification: confirmed need, no budget → MUST transition (graduation #2 alt)
  S05 — borderline ambiguous discovery        → determinism test (3 sub-runs, same decision)

Usage:
    python -m scripts.grad_temp_compare --label pre
    # apply fixes
    python -m scripts.grad_temp_compare --label post
"""

import json
import sys
import argparse
from datetime import datetime
from pathlib import Path


SCENARIOS = [
    {
        "id": "S01",
        "name": "Discovery: бизнес+боль → переход в qualification",
        "focus": "graduation_criteria",
        "expect": "transition",          # must transition by expected_by
        "expected_transition_by": 4,
        "messages": [
            "Здравствуйте",
            "Продуктовый магазин, 1 точка в Алматы. Проблема — постоянные недостачи, не понимаю где теряем товар.",
            "Раньше пробовали Excel, но это уже невозможно",
            "Сколько примерно стоит базовый вариант?",
        ],
    },
    {
        "id": "S02",
        "name": "Discovery: только бизнес, нет боли → остаться в discovery",
        "focus": "graduation_criteria",
        "expect": "stay",               # must NOT transition
        "expected_transition_by": None,
        "messages": [
            "Здравствуйте",
            "Маленький магазин одежды, одна точка",
            "Расскажите о системе",
            "Интересно, какие возможности есть?",
        ],
    },
    {
        "id": "S03",
        "name": "Qualification: бюджет назван явно → переход в presentation",
        "focus": "graduation_criteria",
        "expect": "transition",
        "expected_transition_by": 5,
        "messages": [
            "Здравствуйте",
            "Кофейня, 2 точки в Астане. Проблема — нет единого учёта между точками, данные расходятся.",
            "Нам важна интеграция с Kaspi QR и складской учёт",
            "Бюджет у нас в районе 20 000 тенге в месяц, хотим подключиться в течение месяца",
            "Что именно подойдёт для нашего случая?",
        ],
    },
    {
        "id": "S04",
        "name": "Qualification: потребность подтверждена сильно → переход в presentation",
        "focus": "graduation_criteria",
        "expect": "transition",
        "expected_transition_by": 5,
        "messages": [
            "Здравствуйте",
            "Аптека, 3 точки, Шымкент. Главная боль — расхождение остатков между складом и кассой.",
            "Нам обязательно нужен складской учёт и контроль сроков годности — без этого нельзя работать",
            "Да, это критично, мы готовы внедрять",
            "Что можете предложить конкретно для аптеки?",
        ],
    },
    {
        "id": "S05",
        "name": "Пограничный: вялый интерес без сигналов → детерминированность (3 sub-runs)",
        "focus": "temperature_determinism",
        "expect": "deterministic_stay",  # special: run 3 times, all decisions must be identical
        "expected_transition_by": None,
        "messages": [
            "Здравствуйте",
            "Может быть интересно, у нас небольшой магазин",
            "Ну расскажите что-нибудь про систему",
            "Хм, понятно",
        ],
        "sub_runs": 3,
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


def run_once(scenario: dict, bot) -> dict:
    """Run a single dialog pass, return turns + decision info."""
    bot.reset()
    turns = []
    prev_len = 0

    for i, msg in enumerate(scenario["messages"]):
        result = bot.process(msg)
        turn_num = i + 1

        full_history = get_decision_history(bot)
        new_records = full_history[prev_len:]
        prev_len = len(full_history)

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

    transitioned_at = None
    for t in turns:
        d = t.get("decision")
        if d and d.get("should_transition"):
            transitioned_at = t["turn"]
            break

    return {"turns": turns, "transitioned_at": transitioned_at}


def evaluate_scenario(scenario: dict, bot) -> dict:
    expect = scenario["expect"]
    sub_runs = scenario.get("sub_runs", 1)

    if expect == "deterministic_stay":
        # Run sub_runs times, collect all decisions
        all_passes = []
        for _ in range(sub_runs):
            r = run_once(scenario, bot)
            all_passes.append(r)

        # Check: no premature transition in any run
        transitions = [r["transitioned_at"] for r in all_passes]
        premature = [t for t in transitions if t is not None]

        # Check: all decisions identical across runs (determinism)
        # Compare should_transition decisions turn-by-turn
        all_turn_decisions = []
        for r in all_passes:
            td = tuple(
                (t["turn"], t["decision"]["should_transition"] if t.get("decision") else None)
                for t in r["turns"] if t.get("decision")
            )
            all_turn_decisions.append(td)

        deterministic = len(set(all_turn_decisions)) == 1

        if premature:
            verdict = f"FAIL (premature transition at runs: {premature})"
        elif not deterministic:
            verdict = "FAIL (non-deterministic decisions)"
        else:
            verdict = "PASS"

        return {
            "id": scenario["id"],
            "name": scenario["name"],
            "focus": scenario["focus"],
            "sub_runs": all_passes,
            "transitions": transitions,
            "deterministic": deterministic,
            "verdict": verdict,
        }

    else:
        r = run_once(scenario, bot)
        transitioned_at = r["transitioned_at"]
        expected_by = scenario.get("expected_transition_by")

        if expect == "transition":
            if transitioned_at is None:
                verdict = "FAIL (no transition)"
            elif expected_by and transitioned_at > expected_by:
                verdict = f"LATE (turn {transitioned_at}, expected ≤{expected_by})"
            else:
                verdict = "PASS"
        else:  # stay
            if transitioned_at is not None:
                verdict = f"FAIL (unexpected transition at turn {transitioned_at})"
            else:
                verdict = "PASS"

        return {
            "id": scenario["id"],
            "name": scenario["name"],
            "focus": scenario["focus"],
            "turns": r["turns"],
            "transitioned_at": transitioned_at,
            "expected_transition_by": expected_by,
            "expect": expect,
            "verdict": verdict,
        }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_result(r: dict, label: str):
    icon = "✅" if r["verdict"] == "PASS" else ("⚠️" if "LATE" in r["verdict"] else "❌")
    print(f"\n{icon} {r['id']} [{r['focus']}] — {r['name']}")
    print(f"   Verdict: {r['verdict']}")

    if "sub_runs" in r:
        print(f"   Deterministic: {r['deterministic']} | transitions: {r['transitions']}")
        for run_idx, run in enumerate(r["sub_runs"], 1):
            print(f"\n   ── Sub-run {run_idx}/3 ──")
            for t in run["turns"]:
                d = t.get("decision")
                print(f"     Turn {t['turn']} [{t['state_after']}]")
                print(f"       U: {t['user'][:70]}")
                print(f"       B: {t['bot'][:120]}")
                if d:
                    flag = "→ TRANSIT" if d.get("should_transition") else "  stay   "
                    reas = d.get("reasoning", "")
                    print(f"       Decision: {flag} → {d.get('next_state')}")
                    if reas:
                        print(f"       Reasoning: {reas[:130]}")
    else:
        for t in r.get("turns", []):
            d = t.get("decision")
            print(f"\n   Turn {t['turn']} [{t['state_after']}]")
            print(f"     U: {t['user'][:80]}")
            print(f"     B: {t['bot'][:150]}")
            if d:
                flag = "→ TRANSIT" if d.get("should_transition") else "  stay   "
                reas = d.get("reasoning", "")
                print(f"     Decision: {flag} → {d.get('next_state')}")
                if reas:
                    print(f"     Reasoning: {reas[:150]}")


def print_summary(results: list, label: str):
    total = len(results)
    passed = sum(1 for r in results if r["verdict"] == "PASS")
    print(f"\n{'='*68}")
    print(f"SUMMARY [{label.upper()}]: {passed}/{total} PASS")
    for r in results:
        icon = "✅" if r["verdict"] == "PASS" else ("⚠️" if "LATE" in r["verdict"] else "❌")
        print(f"  {icon} {r['id']}: {r['verdict']}")
    print(f"{'='*68}")
    return passed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="pre", choices=["pre", "post"])
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.bot import SalesBot, setup_autonomous_pipeline
    from src.llm import OllamaLLM

    setup_autonomous_pipeline()

    llm = OllamaLLM()
    bot = SalesBot(llm, flow_name="autonomous")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = []

    print(f"\n{'='*68}")
    print(f"GRAD+TEMP COMPARE [{args.label.upper()}] — {ts}")
    print(f"{'='*68}")

    for scenario in SCENARIOS:
        print(f"\nRunning {scenario['id']} — {scenario['name']} ...", flush=True)
        r = evaluate_scenario(scenario, bot)
        results.append(r)
        icon = "✅" if r["verdict"] == "PASS" else "❌"
        print(f"  {icon} {r['verdict']}", flush=True)

    for r in results:
        print_result(r, args.label)

    passed = print_summary(results, args.label)

    # Save
    results_dir = Path(__file__).parent.parent / "results"
    results_dir.mkdir(exist_ok=True)
    path = results_dir / f"grad_temp_{args.label}_{ts}.json"
    path.write_text(
        json.dumps({"label": args.label, "timestamp": ts, "results": results},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"JSON: {path}")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
