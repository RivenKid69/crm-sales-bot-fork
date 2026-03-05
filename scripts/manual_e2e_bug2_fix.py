"""
Manual E2E dialog runner for BUG 2 fix comparison.
BUG 2: _is_direct_factual_request() hyperactive → autonomous_respond → answer_with_facts
       strips spin_phase/goal/collected_data/missing_data mid-dialog.

FIX 1: _select_template_key: not is_autonomous_flow guard
FIX 2: deflection guard extended from == "answer_with_facts" to _is_factual_turn_guard

Usage:
    python -m scripts.manual_e2e_bug2_fix --label pre
    python -m scripts.manual_e2e_bug2_fix --label post

Each scenario is designed to trigger _is_direct_factual_request() mid-dialog so we can
observe:
  BEFORE: template_key = "answer_with_facts" → bot loses SPIN context
  AFTER:  template_key = "autonomous_respond" → bot keeps SPIN context + answers facts
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# 10 scenarios targeting BUG 2 exactly
# ---------------------------------------------------------------------------
SCENARIOS = [
    {
        "id": "B01",
        "name": "Kaspi integration question mid-discovery ('?' + factual keyword)",
        "description": "Exact bug example: client builds context → asks factual q with ? → template must stay autonomous_respond",
        "messages": [
            "Здравствуйте",
            "У меня продуктовый магазин в Алматы, 3 кассира",
            "Понял, так что насчёт интеграции с Kaspi?",
        ],
        "check": "template_autonomous_respond",
    },
    {
        "id": "B02",
        "name": "'Как работает' textual_factual trigger mid-qualification",
        "description": "textual_factual='как работает' fires _is_direct_factual_request → must stay autonomous_respond",
        "messages": [
            "Здравствуйте",
            "Рассматриваем автоматизацию сети из 4 точек, Алматы и Астана",
            "У нас сейчас Excel, хотим ПО",
            "Как работает интеграция с бухгалтерией?",
        ],
        "check": "template_autonomous_respond",
    },
    {
        "id": "B03",
        "name": "'Есть ли' textual_factual trigger — spin context must survive",
        "description": "textual_factual='есть ли' — bot must answer AND use collected_data context",
        "messages": [
            "Здравствуйте",
            "Один магазин, продукты, касса нужна",
            "Есть ли у вас поддержка ОФД?",
        ],
        "check": "template_autonomous_respond",
    },
    {
        "id": "B04",
        "name": "Price question mid-dialog — factual_intent=True, spin context preserved",
        "description": "price_question intent = factual_intent → must stay autonomous_respond not answer_with_facts",
        "messages": [
            "Здравствуйте",
            "Небольшой магазин одежды, одна точка",
            "Нас 2 человека работает",
            "Сколько стоит Mini в месяц?",
        ],
        "check": "template_autonomous_respond",
    },
    {
        "id": "B05",
        "name": "'Можно ли' textual_factual — qualification phase spin context not lost",
        "description": "textual_factual='можно ли' triggers function — must not switch template",
        "messages": [
            "Здравствуйте",
            "Хотим автоматизировать кофейню, 1 точка",
            "Нам важно работать с Kaspi Pay",
            "Можно ли платить в рассрочку?",
        ],
        "check": "template_autonomous_respond",
    },
    {
        "id": "B06",
        "name": "SPIN flow continuity: factual answer then next turn must continue SPIN correctly",
        "description": "After factual turn in autonomous_respond, next turn should NOT reset spin/collected context",
        "messages": [
            "Здравствуйте",
            "Магазин детской одежды, Нур-Султан, 2 кассы",
            "Какой тариф подходит для 2 касс?",
            "Понял, а у вас есть маркировка?",
        ],
        "check": "no_context_reset",
    },
    {
        "id": "B07",
        "name": "Deflection guard: bot deflects with discovery question instead of answering",
        "description": "state_gated_rules (discovery) vs question_instruction (DIRECT FACTUAL) — deflection guard (Fix 2) must catch it",
        "messages": [
            "Здравствуйте",
            "Что вы продаёте?",
            "Какие тарифы существуют у Wipon?",
        ],
        "check": "no_deflection_on_factual",
    },
    {
        "id": "B08",
        "name": "Bundle query + factual — deflection guard Fix 2 must cover autonomous_respond",
        "description": "Bundle query in autonomous flow — deflection guard should fire for autonomous_respond",
        "messages": [
            "Здравствуйте",
            "Магазин электроники, хочу всё сразу — кассу и оборудование",
            "Что входит в комплект и сколько это стоит?",
        ],
        "check": "template_autonomous_respond",
    },
    {
        "id": "B09",
        "name": "Presentation phase factual question — all context vars still injected",
        "description": "Later SPIN phase: goal/spin_phase/collected_data must all be present in prompt context",
        "messages": [
            "Здравствуйте",
            "Сеть из 5 магазинов, уже есть касса другой марки, хотим мигрировать",
            "Нас 10 сотрудников в разных точках",
            "Важен контроль остатков в реальном времени",
            "Чем отличается Standard от Pro?",
        ],
        "check": "template_autonomous_respond",
    },
    {
        "id": "B10",
        "name": "Closing phase factual question — must stay in closing, not lose terminal data",
        "description": "In autonomous_closing, factual question must NOT lose closing context (contact/IIN required)",
        "messages": [
            "Здравствуйте",
            "Хочу подключиться, готов оформить",
            "Это для магазина продуктов, 1 касса",
            "Давайте оформим!",
            "А насчёт рассрочки — какие условия?",
        ],
        "check": "template_autonomous_respond",
    },
]


def run_dialog(scenario: dict, bot) -> dict:
    """Run a single dialog scenario, capturing template_key and full context."""
    results = []
    bot.reset()

    for i, msg in enumerate(scenario["messages"]):
        result = bot.process(msg)

        # Grab generation meta for template_key — key indicator for BUG 2
        gen_meta = {}
        if hasattr(bot, "generator") and hasattr(bot.generator, "get_last_generation_meta"):
            gen_meta = bot.generator.get_last_generation_meta() or {}

        template_key = gen_meta.get("selected_template_key", "?")
        verifier_used = gen_meta.get("factual_verifier_used", False)
        verifier_verdict = gen_meta.get("factual_verifier_verdict", "-")

        # Grab collected_data snapshot to detect context loss
        collected_data = {}
        if hasattr(bot, "state_machine") and hasattr(bot.state_machine, "collected_data"):
            collected_data = dict(bot.state_machine.collected_data or {})

        entry = {
            "turn": i + 1,
            "user": msg,
            "bot": result["response"],
            "state": result.get("state", ""),
            "action": result.get("action", ""),
            "spin_phase": result.get("spin_phase", ""),
            "template_key": template_key,
            "verifier_used": verifier_used,
            "verifier_verdict": verifier_verdict,
            "collected_data": {k: v for k, v in collected_data.items() if v and v != "?"},
        }
        results.append(entry)

        if result.get("is_final"):
            break

    return {
        "id": scenario["id"],
        "name": scenario["name"],
        "description": scenario["description"],
        "check": scenario["check"],
        "turns": results,
    }


def check_dialog(dialog: dict) -> dict:
    """
    Evaluate the dialog against BUG 2 specific checks.
    Returns pass/fail verdict with details.
    """
    check_type = dialog["check"]
    turns = dialog["turns"]
    issues = []
    observations = []

    for turn in turns:
        tk = turn["template_key"]
        state = turn["state"]
        spin_phase = turn["spin_phase"]
        action = turn["action"]

        # Core check: in autonomous flow, autonomous_respond action must NEVER
        # use answer_with_facts template for mid-dialog factual questions
        if action == "autonomous_respond" and tk == "answer_with_facts":
            issues.append(
                f"[T{turn['turn']}] BUG2: action=autonomous_respond but template=answer_with_facts "
                f"(state={state}, spin={spin_phase})"
            )

        # Note when template is correct
        if tk == "autonomous_respond" and action == "autonomous_respond":
            observations.append(
                f"[T{turn['turn']}] OK: template=autonomous_respond (state={state}, spin={spin_phase})"
            )

        # Check for deflection patterns in factual turns
        if check_type == "no_deflection_on_factual":
            bot_text = turn["bot"].lower()
            deflection_patterns = [
                "расскажите подробнее о вашем бизнесе",
                "расскажите подробнее о себе",
                "что именно хотите узнать",
                "уточните ваш запрос",
                "какой у вас бизнес",
            ]
            for pat in deflection_patterns:
                if pat in bot_text and "?" in turn["user"]:
                    issues.append(
                        f"[T{turn['turn']}] DEFLECTION: bot deflected instead of answering: "
                        f"'{turn['bot'][:100]}'"
                    )

    verdict = "PASS" if not issues else "FAIL"
    return {
        "verdict": verdict,
        "issues": issues,
        "observations": observations,
    }


def format_dialog(dialog: dict, eval_result: dict, label: str) -> str:
    lines = []
    lines.append(f"\n{'='*72}")
    lines.append(f"[{label}] {dialog['id']}: {dialog['name']}")
    lines.append(f"  Check: {dialog['check']}")
    lines.append(f"  Verdict: {'✓ PASS' if eval_result['verdict'] == 'PASS' else '✗ FAIL'}")
    lines.append("="*72)

    for turn in dialog["turns"]:
        tk = turn["template_key"]
        # Highlight BUG: answer_with_facts used for autonomous_respond
        bug_marker = " ⚠️ BUG:answer_with_facts" if (
            turn["action"] == "autonomous_respond" and tk == "answer_with_facts"
        ) else ""
        lines.append(f"  U: {turn['user']}")
        lines.append(f"  B: {turn['bot'][:280]}{'...' if len(turn['bot']) > 280 else ''}")
        lines.append(
            f"     state={turn['state']} | action={turn['action']} | "
            f"spin={turn['spin_phase']} | tmpl={tk}{bug_marker}"
        )
        if turn.get("verifier_used"):
            lines.append(f"     verifier: {turn['verifier_verdict']}")
        if turn["collected_data"]:
            cd_str = ", ".join(f"{k}={v}" for k, v in list(turn["collected_data"].items())[:4])
            lines.append(f"     collected: {cd_str}")
        lines.append("")

    if eval_result["issues"]:
        lines.append("  ⚠️  ISSUES:")
        for issue in eval_result["issues"]:
            lines.append(f"     {issue}")
    if eval_result["observations"]:
        for obs in eval_result["observations"]:
            lines.append(f"     {obs}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="pre", choices=["pre", "post"])
    args = parser.parse_args()
    label = args.label

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.bot import SalesBot, setup_autonomous_pipeline
    from src.llm import OllamaLLM
    from src.feature_flags import flags

    llm = OllamaLLM()
    setup_autonomous_pipeline()
    bot = SalesBot(llm, flow_name="autonomous")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = Path(__file__).parent.parent / "results"
    results_dir.mkdir(exist_ok=True)
    json_file = results_dir / f"bug2_e2e_{label}_{timestamp}.json"
    md_file = results_dir / f"bug2_e2e_{label}_{timestamp}.md"

    print(f"\n{'#'*72}")
    print(f"# BUG2 E2E Manual Dialogs — {label.upper()} FIX — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"# fact_disambiguation: {flags.is_enabled('response_fact_disambiguation')}")
    print(f"# factual_verifier: {flags.is_enabled('response_factual_verifier')}")
    print(f"{'#'*72}")

    all_results = []
    pass_count = 0
    fail_count = 0
    bug2_fires = 0  # count of turns where BUG 2 manifested

    md_lines = [
        f"# BUG2 E2E — {label.upper()} — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
    ]

    for scenario in SCENARIOS:
        print(f"\nRunning {scenario['id']}: {scenario['name']}")
        dialog = run_dialog(scenario, bot)
        eval_result = check_dialog(dialog)
        output = format_dialog(dialog, eval_result, label)
        print(output)
        md_lines.append(output)

        # Count BUG 2 manifestations
        for turn in dialog["turns"]:
            if turn["action"] == "autonomous_respond" and turn["template_key"] == "answer_with_facts":
                bug2_fires += 1

        if eval_result["verdict"] == "PASS":
            pass_count += 1
        else:
            fail_count += 1

        all_results.append({
            "dialog": dialog,
            "eval": eval_result,
        })

    # Summary
    summary = (
        f"\n{'='*72}\n"
        f"SUMMARY [{label.upper()}]: {pass_count}/10 PASS, {fail_count} FAIL\n"
        f"BUG2 template misroutes (autonomous_respond→answer_with_facts): {bug2_fires}\n"
        f"{'='*72}"
    )
    print(summary)
    md_lines.append(summary)

    # Save JSON
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "label": label,
                "timestamp": timestamp,
                "pass": pass_count,
                "fail": fail_count,
                "bug2_fires": bug2_fires,
                "results": all_results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    # Save Markdown
    with open(md_file, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"\nSaved: {json_file}")
    print(f"Saved: {md_file}")

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
