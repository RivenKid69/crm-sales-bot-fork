"""
BUG4 E2E dialog tester — prompt structure inversion.

Tests specifically:
  - do_not_ask compliance (bot re-asks known facts?)
  - spin_phase / goal compliance (bot follows phase-appropriate behaviour?)
  - KB factual grounding (facts reach the LLM despite position?)
  - Deep-dialog stress (turn 8+ with known client context)

Usage:
    python -m scripts.bug4_e2e --label pre  > results/bug4_e2e_pre_<ts>.md
    python -m scripts.bug4_e2e --label post > results/bug4_e2e_post_<ts>.md
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# 10 BUG4-specific scenarios
# Each probes one or more of: do_not_ask, spin_phase, KB grounding.
# ---------------------------------------------------------------------------
SCENARIOS = [
    {
        "id": "B01",
        "name": "do_not_ask: бизнес-тип задан → бот НЕ должен переспрашивать",
        "focus": ["do_not_ask", "spin_phase"],
        "checks": {
            "must_not_contain": ["какой у вас бизнес", "что за бизнес", "расскажите о вашем бизнесе",
                                  "чем занимаетесь", "какой тип бизнеса"],
        },
        "messages": [
            "Здравствуйте",
            "У меня продуктовый магазин, 2 кассы",
            "Интересует автоматизация",
            "Расскажите что умеет система",
            "А какие тарифы есть?",
        ],
    },
    {
        "id": "B02",
        "name": "do_not_ask: имя дано → бот НЕ должен спрашивать имя снова",
        "focus": ["do_not_ask"],
        "checks": {
            "must_not_contain": ["как вас зовут", "как к вам обращаться", "ваше имя"],
        },
        "messages": [
            "Здравствуйте, меня зовут Алия",
            "Интересуюсь вашим продуктом для кафе",
            "Сколько стоит подключение?",
            "А что входит в тариф Mini?",
            "Спасибо, Алия передаст коллегам",  # упомянуть имя — бот не должен снова спросить
        ],
    },
    {
        "id": "B03",
        "name": "spin_phase: discovery → presentation (клиент раскрыл боль, бот двигается вперёд)",
        "focus": ["spin_phase", "goal"],
        "checks": {
            "must_not_contain": ["какой у вас бизнес", "сколько у вас точек", "расскажите подробнее о себе"],
        },
        "messages": [
            "Здравствуйте",
            "Магазин автозапчастей, 3 точки в Алматы",
            "Сейчас учёт ведём в Excel — постоянно ошибки и расхождения",
            "Хотим это исправить",
            "Что именно вы предлагаете для такого бизнеса?",
            "А интеграция с Kaspi есть?",
        ],
    },
    {
        "id": "B04",
        "name": "KB grounding: цена Mini — бот должен дать точную цифру из KB",
        "focus": ["kb_grounding"],
        "checks": {
            "must_contain": ["5 000"],
            "must_not_contain": ["уточню у коллег", "не могу сказать", "свяжитесь"],
        },
        "messages": [
            "Здравствуйте",
            "Небольшой магазин продуктов, одна касса",
            "Сколько стоит Mini в месяц?",
        ],
    },
    {
        "id": "B05",
        "name": "KB grounding: Lite интеграция с Kaspi — факт должен быть в ответе",
        "focus": ["kb_grounding"],
        "checks": {
            "must_contain": ["Kaspi", "Lite"],
            "must_not_contain": ["Mini интегрируется с Kaspi", "Mini поддерживает Kaspi"],
        },
        "messages": [
            "Здравствуйте",
            "Магазин, клиенты часто платят через Kaspi",
            "Какой тариф нужен чтобы принимать оплату через Kaspi?",
        ],
    },
    {
        "id": "B06",
        "name": "do_not_ask + KB: контакт дан → в closing не переспрашивать, коллега позвонит",
        "focus": ["do_not_ask", "spin_phase"],
        "checks": {
            "must_not_contain": ["как с вами связаться", "ваш телефон", "оставьте номер"],
        },
        "messages": [
            "Здравствуйте",
            "Продуктовый магазин, 1 касса, Астана",
            "Хочу подключиться к Mini",
            "Мой телефон +77012345678",
            "Когда позвонят?",
        ],
    },
    {
        "id": "B07",
        "name": "spin_phase: бот НЕ задаёт вопросы discovery когда клиент уже в presentation",
        "focus": ["spin_phase", "do_not_ask"],
        "checks": {
            "must_not_contain": ["расскажите о вашем бизнесе", "чем занимаетесь", "сколько точек"],
        },
        "messages": [
            "Здравствуйте",
            "Сеть аптек, 5 точек, Алматы. Сейчас на 1С, хотим перейти",
            "Какие тарифы для сети из 5 точек?",
            "А что с поддержкой при переходе?",
            "Мне важна скорость интеграции",
            "Как быстро можно подключить 5 точек?",
        ],
    },
    {
        "id": "B08",
        "name": "Deep dialog (8 ходов): do_not_ask соблюдается на поздних ходах",
        "focus": ["do_not_ask", "spin_phase"],
        "checks": {
            "must_not_contain": ["какой у вас бизнес", "что за бизнес", "расскажите о вашем"],
        },
        "messages": [
            "Здравствуйте",
            "Кафе в Шымкенте, 30 посадочных мест",
            "Сейчас нет никакой автоматизации",
            "Проблема — не понимаем что продаётся лучше всего",
            "И часто ошибки при расчёте сдачи",
            "Сколько стоит подключение?",
            "Что входит в базовый тариф?",
            "А есть ли поддержка на казахском языке?",
        ],
    },
    {
        "id": "B09",
        "name": "objection handling: «дорого» → бот работает с возражением, не игнорирует",
        "focus": ["spin_phase", "goal"],
        "checks": {
            "must_not_contain": ["хорошо", "понял", "окей"],  # не игнорирует возражение
        },
        "messages": [
            "Здравствуйте",
            "Небольшой магазин хозтоваров, одна точка",
            "Что предлагаете?",
            "Сколько стоит?",
            "Это дорого для меня",
            "Я не готов платить столько",
        ],
    },
    {
        "id": "B10",
        "name": "KB grounding + do_not_ask: вопрос о функциях Standard → точный ответ без переспросов",
        "focus": ["kb_grounding", "do_not_ask"],
        "checks": {
            "must_contain": ["Standard"],
            "must_not_contain": ["расскажите подробнее", "что именно вас интересует в Standard",
                                  "уточните пожалуйста"],
        },
        "messages": [
            "Здравствуйте",
            "Магазин электроники, 2 точки в Алматы",
            "Что умеет тариф Standard? Мне важны детали",
        ],
    },
]


# ---------------------------------------------------------------------------
# Checks runner
# ---------------------------------------------------------------------------

def run_checks(scenario: dict, turns: list) -> list:
    """Run must_contain / must_not_contain checks over all bot responses."""
    issues = []
    checks = scenario.get("checks", {})
    all_bot_text = " ".join(t["bot"].lower() for t in turns)

    for phrase in checks.get("must_contain", []):
        if phrase.lower() not in all_bot_text:
            issues.append(f"FAIL must_contain: '{phrase}' NOT found in bot responses")

    for phrase in checks.get("must_not_contain", []):
        if phrase.lower() in all_bot_text:
            # Find which turn
            for t in turns:
                if phrase.lower() in t["bot"].lower():
                    issues.append(
                        f"FAIL must_not_contain: '{phrase}' found at turn {t['turn']}: "
                        f"«{t['bot'][:120]}»"
                    )
                    break

    return issues


# ---------------------------------------------------------------------------
# Dialog runner
# ---------------------------------------------------------------------------

def run_dialog(scenario: dict, bot) -> dict:
    bot.reset()
    turns = []
    for i, msg in enumerate(scenario["messages"]):
        result = bot.process(msg)
        turns.append({
            "turn": i + 1,
            "user": msg,
            "bot": result["response"],
            "state": result.get("state", ""),
            "action": result.get("action", ""),
            "spin_phase": result.get("spin_phase", ""),
            "template": result.get("template_key", ""),
        })
        if result.get("is_final"):
            break

    issues = run_checks(scenario, turns)
    return {
        "id": scenario["id"],
        "name": scenario["name"],
        "focus": scenario["focus"],
        "turns": turns,
        "issues": issues,
        "passed": len(issues) == 0,
    }


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------

def print_report(dialogs: list, label: str) -> str:
    lines = []
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append(f"# BUG4 E2E Report — {label.upper()} — {ts}\n")

    passed = sum(1 for d in dialogs if d["passed"])
    lines.append(f"## Summary: {passed}/{len(dialogs)} PASS\n")

    for d in dialogs:
        status = "✅ PASS" if d["passed"] else "❌ FAIL"
        lines.append(f"---\n### {d['id']} {status} — {d['name']}")
        lines.append(f"Focus: {', '.join(d['focus'])}\n")
        for t in d["turns"]:
            lines.append(f"**U{t['turn']}:** {t['user']}")
            bot_preview = t["bot"][:400] + ("…" if len(t["bot"]) > 400 else "")
            lines.append(f"**B{t['turn']}:** {bot_preview}")
            lines.append(f"  `[{t['state']}] action={t['action']} spin={t['spin_phase']} tpl={t['template']}`")
            lines.append("")
        if d["issues"]:
            lines.append("**Issues:**")
            for issue in d["issues"]:
                lines.append(f"- {issue}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="pre", choices=["pre", "post"])
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.bot import SalesBot
    from src.llm import OllamaLLM

    llm = OllamaLLM()
    bot = SalesBot(llm, flow_name="autonomous")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = Path(__file__).parent.parent / "results"
    results_dir.mkdir(exist_ok=True)
    json_path = results_dir / f"bug4_e2e_{args.label}_{ts}.json"
    md_path = results_dir / f"bug4_e2e_{args.label}_{ts}.md"

    all_dialogs = []
    for scenario in SCENARIOS:
        print(f"Running {scenario['id']}: {scenario['name']} ...", flush=True)
        dialog = run_dialog(scenario, bot)
        all_dialogs.append(dialog)
        status = "PASS" if dialog["passed"] else f"FAIL ({len(dialog['issues'])} issues)"
        print(f"  → {status}", flush=True)
        if dialog["issues"]:
            for issue in dialog["issues"]:
                print(f"     {issue}", flush=True)

    report = print_report(all_dialogs, args.label)
    md_path.write_text(report, encoding="utf-8")
    json_path.write_text(
        json.dumps({"label": args.label, "timestamp": ts, "dialogs": all_dialogs},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    passed = sum(1 for d in all_dialogs if d["passed"])
    print(f"\n{'='*60}")
    print(f"RESULT: {passed}/{len(all_dialogs)} PASS")
    print(f"Report: {md_path}")
    print(f"JSON:   {json_path}")


if __name__ == "__main__":
    main()
