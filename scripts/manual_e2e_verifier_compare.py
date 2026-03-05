"""
Pre/post comparison dialogs for FactualVerifier context-loss fix.
Tests all 5 changes from the plan:
  Change 1 — paraphrase detection in _build_prompt
  Change 2 — dialog_history in verifier prompt
  Change 3 — pass1 rewrite_response as fallback
  Change 4 — strip phrase in _ensure_no_forbidden_fallback
  Change 5 — strip phrase in _enforce_no_colleague_fallback

Usage:
    python -m scripts.manual_e2e_verifier_compare --label pre
    python -m scripts.manual_e2e_verifier_compare --label post
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

SCENARIOS = [
    # ------------------------------------------------------------------
    # D01 — General features (Change 1: paraphrase should PASS)
    # ------------------------------------------------------------------
    {
        "id": "D01",
        "name": "General features — paraphrase should pass verifier (Change 1)",
        "area": "Change1",
        "messages": [
            "Здравствуйте",
            "Чем занимается ваша система?",
            "Какие интеграции с банками у вас есть?",
        ],
    },
    # ------------------------------------------------------------------
    # D02 — Price question with numeric (Change 1: numeric still strict)
    # ------------------------------------------------------------------
    {
        "id": "D02",
        "name": "Price question Mini — numeric grounding must stay strict (Change 1)",
        "area": "Change1",
        "messages": [
            "Здравствуйте",
            "У нас небольшой продуктовый магазин, 1 касса",
            "Сколько стоит тариф Mini?",
        ],
    },
    # ------------------------------------------------------------------
    # D03 — Support question (Change 4+5: 'коллега позвонит' stripped, not full replace)
    # ------------------------------------------------------------------
    {
        "id": "D03",
        "name": "Support 24/7 — forbidden phrase stripped not whole response (Change 4+5)",
        "area": "Change4+5",
        "messages": [
            "Здравствуйте",
            "Есть ли у вас техническая поддержка?",
            "А поддержка работает 24/7?",
        ],
    },
    # ------------------------------------------------------------------
    # D04 — Multi-turn context (Change 2: history injected, verifier sees it)
    # ------------------------------------------------------------------
    {
        "id": "D04",
        "name": "Multi-turn context — verifier should see dialog history (Change 2)",
        "area": "Change2",
        "messages": [
            "Здравствуйте",
            "У нас сеть из 5 магазинов по Алматы",
            "Нас интересует тариф Pro для сети",
            "Что конкретно входит в Pro для нашего масштаба?",
        ],
    },
    # ------------------------------------------------------------------
    # D05 — Objection + factual (Change 3: rewrite_response fallback > db_only)
    # ------------------------------------------------------------------
    {
        "id": "D05",
        "name": "Objection about price — rewrite fallback should preserve context (Change 3)",
        "area": "Change3",
        "messages": [
            "Здравствуйте",
            "У нас небольшой магазин",
            "Мне кажется ваша система дороговата",
            "Что входит в базовый тариф за эту цену?",
        ],
    },
    # ------------------------------------------------------------------
    # D06 — Features vs ordinary cash register (Change 1: comparative paraphrase)
    # ------------------------------------------------------------------
    {
        "id": "D06",
        "name": "Features comparison — paraphrase of comparative statements (Change 1)",
        "area": "Change1",
        "messages": [
            "Здравствуйте",
            "Чем ваша система лучше обычной кассы?",
            "У вас есть учёт склада?",
        ],
    },
    # ------------------------------------------------------------------
    # D07 — Security / data question (Change 4+5: colleague phrase risk)
    # ------------------------------------------------------------------
    {
        "id": "D07",
        "name": "Data security question — phrase strip not full replace (Change 4+5)",
        "area": "Change4+5",
        "messages": [
            "Здравствуйте",
            "Как вы обеспечиваете безопасность данных?",
            "Где хранятся данные, на серверах в Казахстане?",
        ],
    },
    # ------------------------------------------------------------------
    # D08 — Detailed multi-turn (Change 2: history gives verifier context)
    # ------------------------------------------------------------------
    {
        "id": "D08",
        "name": "Detailed SPIN flow — history context helps verifier (Change 2)",
        "area": "Change2",
        "messages": [
            "Здравствуйте",
            "Мы занимаемся розничной торговлей, 3 кассы",
            "Больше всего проблемы с учётом товаров",
            "Какой тариф лучше подойдёт нам?",
            "Расскажи подробнее про Standard",
        ],
    },
    # ------------------------------------------------------------------
    # D09 — Reports / export (Change 3: rewrite vs db-only)
    # ------------------------------------------------------------------
    {
        "id": "D09",
        "name": "Reports & export — rewrite_response fallback quality (Change 3)",
        "area": "Change3",
        "messages": [
            "Здравствуйте",
            "Какие отчёты можно строить в системе?",
            "А можно ли экспортировать отчёты в Excel?",
        ],
    },
    # ------------------------------------------------------------------
    # D10 — Full pipeline: closing + factual (all changes together)
    # ------------------------------------------------------------------
    {
        "id": "D10",
        "name": "Full pipeline: closing flow + factual question (all Changes)",
        "area": "All",
        "messages": [
            "Здравствуйте, хочу подключиться",
            "Сколько стоит тариф Mini на год?",
            "Хорошо, мой телефон 87015551234",
        ],
    },
]


def run_dialog(scenario: dict, bot) -> dict:
    results = []
    bot.reset()

    for i, msg in enumerate(scenario["messages"]):
        result = bot.process(msg)
        entry = {
            "turn": i + 1,
            "user": msg,
            "bot": result.get("response", ""),
            "state": result.get("state", ""),
            "action": result.get("action", ""),
            "spin_phase": result.get("spin_phase", ""),
            # verifier meta if available
            "verifier_used": result.get("factual_verifier_used", False),
            "verifier_changed": result.get("factual_verifier_changed", False),
            "verifier_verdict": result.get("factual_verifier_verdict", ""),
            "verifier_reason_codes": result.get("factual_verifier_reason_codes", []),
        }
        results.append(entry)

        if result.get("is_final"):
            break

    return {
        "id": scenario["id"],
        "name": scenario["name"],
        "area": scenario["area"],
        "turns": results,
    }


def check_issues(dialog: dict) -> list:
    issues = []
    for turn in dialog["turns"]:
        bot_text = turn["bot"]

        # Check: forbidden phrase leaked into final response
        if any(p in bot_text for p in ["коллега позвонит", "уточню у коллег", "вернусь с ответом", "передам вопрос коллег"]):
            issues.append(f"[T{turn['turn']}] FORBIDDEN PHRASE in response: {bot_text[:120]}")

        # Check: db_only_rewrite happened (context loss)
        if "db_only_rewrite" in turn.get("verifier_reason_codes", []):
            issues.append(f"[T{turn['turn']}] DB_ONLY fallback triggered (context loss risk): {bot_text[:120]}")

        # Check: response is just a raw KB sentence (very short, no dialog markers)
        if turn["verifier_changed"] and len(bot_text) < 80:
            issues.append(f"[T{turn['turn']}] SHORT response after verifier change (raw KB?): {bot_text!r}")

        # Check: НЕ ПУТАТЬ internal instruction leaked
        if "НЕ ПУТАТЬ" in bot_text:
            issues.append(f"[T{turn['turn']}] НЕ ПУТАТЬ leaked: {bot_text[:80]}")

    return issues


def print_dialog(dialog: dict, label: str) -> str:
    lines = []
    lines.append(f"\n{'='*72}")
    lines.append(f"[{label.upper()}] {dialog['id']}: {dialog['name']}")
    lines.append(f"Area: {dialog['area']}")
    lines.append("=" * 72)
    for turn in dialog["turns"]:
        v_info = ""
        if turn.get("verifier_used"):
            codes = ",".join(turn.get("verifier_reason_codes", []))
            v_info = f" [VER:{turn.get('verifier_verdict','')}:{codes}]"
        lines.append(f"  U: {turn['user']}")
        lines.append(f"  B: {turn['bot'][:350]}{'...' if len(turn['bot']) > 350 else ''}")
        lines.append(f"     [{turn['state']}] {turn['action']} {turn['spin_phase']}{v_info}")
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

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.bot import SalesBot, setup_autonomous_pipeline
    from src.llm import OllamaLLM

    llm = OllamaLLM()
    setup_autonomous_pipeline()
    bot = SalesBot(llm, flow_name="autonomous")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(__file__).parent.parent / "results"
    output_dir.mkdir(exist_ok=True)
    output_json = output_dir / f"verifier_e2e_{args.label}_{timestamp}.json"
    output_md = output_dir / f"verifier_e2e_{args.label}_{timestamp}.md"

    all_results = []
    md_lines = []
    md_lines.append(f"# FactualVerifier E2E — {args.label.upper()} — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    md_lines.append("")

    for scenario in SCENARIOS:
        print(f"Running {scenario['id']}: {scenario['name']} ...", flush=True)
        dialog = run_dialog(scenario, bot)
        output = print_dialog(dialog, args.label)
        print(output)
        md_lines.append(output)
        all_results.append(dialog)

    # Summary
    print(f"\n{'='*72}")
    print("ISSUES SUMMARY")
    print("=" * 72)
    total_issues = 0
    for dialog in all_results:
        issues = check_issues(dialog)
        total_issues += len(issues)
        status = f"⚠️  {len(issues)} issue(s)" if issues else "OK"
        print(f"  {dialog['id']} [{dialog['area']}]: {status}")
        for iss in issues:
            print(f"      {iss}")

    print(f"\nTotal issues: {total_issues}")

    md_lines.append(f"\n## Issues Summary: {total_issues} total\n")
    for dialog in all_results:
        issues = check_issues(dialog)
        if issues:
            md_lines.append(f"- **{dialog['id']}**: {'; '.join(issues[:3])}")

    # Save outputs
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(
            {"label": args.label, "timestamp": timestamp, "scenarios": all_results},
            f,
            ensure_ascii=False,
            indent=2,
        )
    with open(output_md, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"\n✅ JSON: {output_json}")
    print(f"✅ MD:   {output_md}")


if __name__ == "__main__":
    main()
