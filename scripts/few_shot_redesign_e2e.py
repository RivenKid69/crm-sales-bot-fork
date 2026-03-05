#!/usr/bin/env python3
"""
FEW-SHOT REDESIGN E2E — 3 целевых сценария.

Запускать ДО и ПОСЛЕ изменений для наглядного сравнения.

Фокус:
  S1: "подумаю" (голое слово) → objection_think, не rejection
      Нет паттерна для "подумаю" без предиката → LLM. n=5 first 5 = нет objection_think.
  S2: Скептик — невидимые интенты (idx 6-14 не попадают при n=5)
      objection_competitor, problem_revealed, objection_timing, info_provided
  S3: "3 точки" как ответ → situation_provided, не price_question
      Контекстно-зависимый ответ на вопрос бота о количестве точек.

Использование:
  python -m scripts.few_shot_redesign_e2e --label pre   # до изменений
  python -m scripts.few_shot_redesign_e2e --label post  # после изменений
  python -m scripts.few_shot_redesign_e2e --compare pre post  # сравнение
"""

import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

# ─────────────────────────────────────────────────────────────────────────────
# СЦЕНАРИИ
# critical_turns: {turn_idx (0-based): {"expect": intent, "note": str}}
# ─────────────────────────────────────────────────────────────────────────────
SCENARIOS = [
    # ═══════════════════════════════════════════════════════════════════════
    # S1: "подумаю" — objection_think, НЕ rejection/objection_timing
    #
    # Голое "подумаю" без предиката ("надо подумать", "дайте подумать") —
    # нет паттерна → LLM классификатор.
    # При n=5 (first 5 examples): greeting, price_q, situation, demo_req, brevity
    # → нет objection_think → LLM гадает → обычно rejection или objection_timing
    #
    # После fix: n=12, есть anchor objection_price + context-matched objection_think
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "S1",
        "name": "подумаю — objection_think без паттерна",
        "critical_turns": {
            3: {
                "expect": "objection_think",
                "accept": ["objection_think"],
                "note": "голое 'подумаю' = objection_think, не rejection/timing",
            },
            6: {
                "expect": "objection_think",
                "accept": ["objection_think"],
                "note": "'подумаю, посоветуюсь с партнёром' = objection_think повторно",
            },
        },
        "turns": [
            {"msg": "Добрый день"},
            {"msg": "У меня магазин косметики в Нур-Султане, одна точка, 2 кассира"},
            {"msg": "Расскажите подробнее о Standard тарифе"},
            {"msg": "подумаю"},  # ← КЛЮЧЕВОЙ: нет паттерна, только LLM
            {"msg": "А чем вы лучше Poster?"},
            {"msg": "Сколько стоит Standard для одной точки?"},
            {"msg": "подумаю, посоветуюсь с партнёром"},  # ← КЛЮЧЕВОЙ: развёрнутый вариант
            {"msg": "Ладно, убедили. Давайте оформим Standard"},
            {"msg": "87051234567"},
        ],
    },

    # ═══════════════════════════════════════════════════════════════════════
    # S2: Скептик — невидимые интенты (idx 6-14 при n=5 не показываются)
    #
    # При n=5 LLM НЕ видит примеров для:
    #   - objection_competitor (idx 6: "у нас Poster, зачем нам вы?")
    #   - rejection (idx 10: "Нет, нам не интересно")
    #   - objection_timing (idx 11: "не сейчас")
    #   - objection_price (idx 12: "Это слишком дорого")
    #   - info_provided (idx 13: "Султан")
    #   - problem_revealed (idx 14: "теряем клиентов...")
    #
    # Этот сценарий собирает 4 таких интента в одном диалоге.
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "S2",
        "name": "Скептик — невидимые интенты idx 6-14",
        "critical_turns": {
            2: {
                "expect": "objection_competitor",
                "accept": ["objection_competitor", "comparison"],
                "note": "'у нас 1С стоит, зачем менять' = objection_competitor",
            },
            3: {
                "expect": "problem_revealed",
                "accept": ["problem_revealed"],
                "note": "'расхождения остатков между складом и кассой' = problem_revealed",
            },
            5: {
                "expect": "objection_price",
                "accept": ["objection_price"],
                "note": "'для нас дороговато' = objection_price",
            },
            7: {
                "expect": "objection_timing",
                "accept": ["objection_timing", "objection_no_time"],
                "note": "'не сейчас, может через месяц' = objection_timing",
            },
        },
        "turns": [
            {"msg": "Добрый день"},
            {"msg": "У меня 2 магазина бытовой химии в Караганде"},
            {"msg": "У нас 1С стоит, зачем нам менять на ваше?"},  # ← objection_competitor
            {"msg": "Ну вот у нас постоянные расхождения остатков между складом и кассой"},  # ← problem_revealed
            {"msg": "Ок, и как вы это решаете? Сколько стоит для двух точек?"},
            {"msg": "Для нас дороговато"},  # ← objection_price
            {"msg": "А рассрочка есть?"},
            {"msg": "Не сейчас, может через месяц вернусь к вопросу"},  # ← objection_timing
            {"msg": "Хорошо, запишите мой номер: 87021234567"},
        ],
    },

    # ═══════════════════════════════════════════════════════════════════════
    # S3: "3 точки" — situation_provided, НЕ price_question
    #
    # Клиент отвечает на вопрос бота коротко: "3 точки".
    # Без контекста LLM может дать price_question (сколько стоит для 3 точек?).
    # С контекстом (бот спросил "сколько у вас точек") → situation_provided.
    #
    # После fix: context-matched пример {"spin_phase": "discovery"} для "3 точки"
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "S3",
        "name": "3 точки = situation_provided, не price_question",
        "critical_turns": {
            2: {
                "expect": "situation_provided",
                "accept": ["situation_provided", "info_provided"],
                "note": "'3 точки' в discovery как ответ = situation_provided",
            },
            4: {
                "expect": "price_question",
                "accept": ["price_question", "pricing_details"],
                "note": "'для 3 точек сколько выйдет' = price_question (не situation!)",
            },
        },
        "turns": [
            {"msg": "Здравствуйте"},
            {"msg": "У меня сеть продуктовых магазинов"},
            {"msg": "3 точки"},  # ← КЛЮЧЕВОЙ: ответ на вопрос бота, не ценовой запрос
            {"msg": "Нам нужна централизованная аналитика и контроль кассиров"},
            {"msg": "Для 3 точек сколько выйдет Standard?"},  # ← а вот ЭТО price_question
            {"msg": "Подходит. Давайте оформим"},
            {"msg": "87015554433"},
        ],
    },
]

DIVIDER = "─" * 80


def run_dialog(scenario: dict, bot) -> dict:
    """Запускает один диалог, собирает метаданные + pass/fail по critical turns."""
    bot.reset()
    turns = []
    critical = scenario.get("critical_turns", {})
    results_summary = {}

    for i, turn_spec in enumerate(scenario["turns"]):
        msg = turn_spec["msg"] if isinstance(turn_spec, dict) else turn_spec
        t0 = time.time()
        result = bot.process(msg)
        elapsed = time.time() - t0

        intent = result.get("intent", "?")
        confidence = result.get("confidence", 0)

        turn_data = {
            "turn": i,
            "user": msg,
            "bot": result["response"],
            "state": result.get("state", "?"),
            "action": result.get("action", "?"),
            "spin_phase": result.get("spin_phase", "?"),
            "intent": intent,
            "confidence": round(confidence, 3) if isinstance(confidence, float) else confidence,
            "template_key": result.get("template_key", "?"),
            "elapsed_s": round(elapsed, 2),
            "is_final": result.get("is_final", False),
        }

        # Check critical turn
        if i in critical:
            spec = critical[i]
            accepted = spec.get("accept", [spec["expect"]])
            passed = intent in accepted
            turn_data["critical"] = True
            turn_data["expected"] = spec["expect"]
            turn_data["accepted"] = accepted
            turn_data["passed"] = passed
            turn_data["note"] = spec["note"]
            results_summary[i] = {
                "expected": spec["expect"],
                "actual": intent,
                "passed": passed,
                "note": spec["note"],
            }

        turns.append(turn_data)
        if result.get("is_final"):
            break

    passed_count = sum(1 for v in results_summary.values() if v["passed"])
    total_critical = len(results_summary)

    return {
        "id": scenario["id"],
        "name": scenario["name"],
        "turns": turns,
        "critical_results": results_summary,
        "passed": passed_count,
        "total_critical": total_critical,
        "all_passed": passed_count == total_critical,
    }


def format_dialog(d: dict) -> str:
    """Форматирует диалог с pass/fail для critical turns."""
    lines = [
        f"\n{'='*80}",
        f"  {d['id']} | {d['name']}",
        f"  Critical: {d['passed']}/{d['total_critical']} PASS",
        f"{'='*80}",
    ]

    for t in d["turns"]:
        lines.append(DIVIDER)
        is_crit = t.get("critical", False)
        marker = ""
        if is_crit:
            marker = " PASS" if t["passed"] else " FAIL"
            marker = f" [{marker}]"

        meta = (
            f"T{t['turn']} | intent={t['intent']} (conf={t['confidence']}) "
            f"| state={t['state']} | spin={t['spin_phase']}{marker}"
        )
        lines.append(f"  [{meta}]")

        if is_crit:
            status = "PASS" if t["passed"] else "FAIL"
            lines.append(
                f"  >>> {status}: expected={t['expected']} actual={t['intent']} "
                f"accepted={t['accepted']}"
            )
            lines.append(f"  >>> {t['note']}")

        lines.append(f"  КЛИЕНТ: {t['user']}")
        bot_resp = t["bot"]
        if len(bot_resp) > 200:
            bot_resp = bot_resp[:200] + "..."
        lines.append(f"  БОТ:    {bot_resp}")

        if t["is_final"]:
            lines.append("  ФИНАЛ")
        lines.append("")

    return "\n".join(lines)


def run_all(label: str):
    """Запускает все сценарии, сохраняет результаты."""
    from src.bot import SalesBot, setup_autonomous_pipeline
    from src.llm import OllamaLLM

    setup_autonomous_pipeline()

    llm = OllamaLLM()
    bot = SalesBot(llm, flow_name="autonomous")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = Path(__file__).parent.parent / "results" / f"few_shot_e2e_{label}_{ts}.json"
    json_path.parent.mkdir(exist_ok=True)

    all_results = []
    total_pass = 0
    total_crit = 0

    print(f"\n{'='*80}")
    print(f"  FEW-SHOT REDESIGN E2E — label={label}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*80}")

    for scenario in SCENARIOS:
        print(f"\n>>> [{scenario['id']}] {scenario['name']} ({len(scenario['turns'])} turns)...")
        dialog = run_dialog(scenario, bot)
        print(format_dialog(dialog))
        all_results.append(dialog)
        total_pass += dialog["passed"]
        total_crit += dialog["total_critical"]

    # Summary
    print(f"\n{'='*80}")
    print(f"  ИТОГО: {total_pass}/{total_crit} critical turns PASS")
    print(f"{'='*80}")
    for d in all_results:
        status = "ALL PASS" if d["all_passed"] else "FAIL"
        print(f"  {d['id']}: {d['passed']}/{d['total_critical']} — {status}")
        for turn_idx, cr in d["critical_results"].items():
            mark = "PASS" if cr["passed"] else "FAIL"
            print(f"       T{turn_idx}: [{mark}] expected={cr['expected']} actual={cr['actual']}")
    print(f"{'='*80}")

    # Save JSON
    output = {
        "label": label,
        "timestamp": ts,
        "total_pass": total_pass,
        "total_critical": total_crit,
        "scenarios": all_results,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"  Сохранено: {json_path}")

    return json_path


def compare(label_pre: str, label_post: str):
    """Сравнивает два прогона по label."""
    results_dir = Path(__file__).parent.parent / "results"

    def find_latest(label):
        files = sorted(results_dir.glob(f"few_shot_e2e_{label}_*.json"), reverse=True)
        if not files:
            print(f"  Не найден файл для label={label}")
            sys.exit(1)
        return files[0]

    pre_path = find_latest(label_pre)
    post_path = find_latest(label_post)

    with open(pre_path) as f:
        pre = json.load(f)
    with open(post_path) as f:
        post = json.load(f)

    print(f"\n{'='*80}")
    print(f"  СРАВНЕНИЕ: {label_pre} vs {label_post}")
    print(f"  PRE:  {pre_path.name}")
    print(f"  POST: {post_path.name}")
    print(f"{'='*80}")
    print(f"\n  Общий результат: {pre['total_pass']}/{pre['total_critical']} → {post['total_pass']}/{post['total_critical']}")
    print()

    for s_pre, s_post in zip(pre["scenarios"], post["scenarios"]):
        sid = s_pre["id"]
        print(f"  {sid}: {s_pre['name']}")
        print(f"     {s_pre['passed']}/{s_pre['total_critical']} → {s_post['passed']}/{s_post['total_critical']}")

        # Merge critical turn keys
        all_turns = set(s_pre["critical_results"].keys()) | set(s_post["critical_results"].keys())
        for tk in sorted(all_turns):
            cr_pre = s_pre["critical_results"].get(str(tk), s_pre["critical_results"].get(tk, {}))
            cr_post = s_post["critical_results"].get(str(tk), s_post["critical_results"].get(tk, {}))

            pre_intent = cr_pre.get("actual", "?")
            post_intent = cr_post.get("actual", "?")
            pre_pass = cr_pre.get("passed", False)
            post_pass = cr_post.get("passed", False)

            delta = ""
            if not pre_pass and post_pass:
                delta = " FIXED"
            elif pre_pass and not post_pass:
                delta = " REGRESSED"
            elif pre_pass and post_pass:
                delta = " OK"
            else:
                delta = " STILL FAIL"

            pre_mark = "PASS" if pre_pass else "FAIL"
            post_mark = "PASS" if post_pass else "FAIL"
            print(
                f"       T{tk}: {pre_intent} [{pre_mark}] → {post_intent} [{post_mark}]{delta}"
            )
        print()

    print(f"{'='*80}")


def main():
    parser = argparse.ArgumentParser(description="Few-shot redesign E2E test")
    parser.add_argument("--label", type=str, help="Label for this run (e.g. 'pre' or 'post')")
    parser.add_argument("--compare", nargs=2, metavar=("PRE", "POST"), help="Compare two labels")
    args = parser.parse_args()

    if args.compare:
        compare(args.compare[0], args.compare[1])
    elif args.label:
        run_all(args.label)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
