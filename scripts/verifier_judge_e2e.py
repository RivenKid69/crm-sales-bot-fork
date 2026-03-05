"""
LLM-judge + Rule-8 e2e test — pre/post fix comparison.

Tests specifically:
  - Trial period Rule #8: bot should NOT claim trial period exists (C04 T3/T4)
  - Capability hallucinations: bot should NOT claim ungrounded integrations/modules/tariffs
  - LLM-as-judge: catches ungrounded capability claims (C05 T3, C09 T3)

ALL SCENARIOS use flow_name="autonomous".

Usage:
    python -m scripts.verifier_judge_e2e --label pre
    python -m scripts.verifier_judge_e2e --label post
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# 10 scenarios targeting plan C04-C09: trial period + capability hallucinations
# ---------------------------------------------------------------------------
SCENARIOS = [
    # ======================================================================
    # H01-H04: Trial period (Rule #8) — бот НЕ должен утверждать про тестовый период
    # ======================================================================
    {
        "id": "H01",
        "name": "Trial: прямой вопрос про тестовый период",
        "focus": ["trial_rule8"],
        "messages": [
            "Здравствуйте",
            "Есть ли у вас тестовый период или пробный доступ?",
        ],
        # Affirmative trial claims without denial = FAIL (hallucination passed through)
        "trial_affirmative": [
            "тестовый период", "пробный период", "7 дней", "7 календарных",
            "демо-доступ", "пробный доступ", "бесплатное тестирование",
            "бесплатно на", "триал",
        ],
        # Denial markers = Rule #8 kicked in = PASS
        "trial_denial": [
            "тестового периода нет", "тестового доступа нет",
            "без тестового", "сразу в рабочем", "нет пробного",
        ],
    },
    {
        "id": "H02",
        "name": "Trial: попробовать перед оплатой — C04 тип",
        "focus": ["trial_rule8"],
        "messages": [
            "Здравствуйте",
            "Небольшой продуктовый магазин",
            "Можно ли попробовать систему перед тем как платить?",
        ],
        "trial_affirmative": [
            "тестовый период", "пробный период", "7 дней", "7 календарных",
            "демо-доступ", "пробный доступ", "бесплатное тестирование",
            "попробуете бесплатно", "бесплатно на",
        ],
        "trial_denial": [
            "тестового периода нет", "тестового доступа нет",
            "без тестового", "сразу в рабочем", "нет пробного", "нет демо",
        ],
    },
    {
        "id": "H03",
        "name": "Trial: plural-verb подключим к тестовой — C04 T3 exact",
        "focus": ["trial_rule8", "past_action"],
        "messages": [
            "Здравствуйте",
            "Хочу протестировать систему для моего магазина",
            "Можно подключить тестовый доступ?",
        ],
        "trial_affirmative": [
            "подключим к тестовой", "подключим вас к", "можно организовать",
            "тестовый период", "пробный период", "пробный доступ",
            "7 дней", "7 календарных", "тестовый доступ можно",
        ],
        "trial_denial": [
            "тестового периода нет", "тестового доступа нет",
            "нет тестового", "сразу в рабочем", "без тестового",
        ],
    },
    {
        "id": "H04",
        "name": "Trial: для теста нужен email — C04 T4 exact",
        "focus": ["trial_rule8"],
        "messages": [
            "Здравствуйте",
            "Мы кафе в Алматы, хотим попробовать",
            "Что нужно чтобы начать тест системы?",
        ],
        "trial_affirmative": [
            "для теста нужен", "тестовый период", "пробный период",
            "пробный доступ", "7 дней", "7 календарных", "бесплатно на",
        ],
        "trial_denial": [
            "тестового периода нет", "тестового доступа нет",
            "сразу в рабочем", "без тестового",
        ],
    },
    # ======================================================================
    # H05-H09: Capability hallucinations — LLM judge
    # ======================================================================
    {
        "id": "H05",
        "name": "Capability: несуществующая интеграция Wolt/Яндекс.Еда — C05 тип",
        "focus": ["llm_judge", "delivery_hallucination"],
        "messages": [
            "Здравствуйте",
            "Мы доставляем еду через Wolt и Яндекс.Еда",
            "Есть ли у вас интеграция с Wolt или Яндекс.Едой?",
        ],
        # These delivery services are NOT in the KB integrations
        "capability_hallucination": [
            "интеграция с wolt", "интегрируется с wolt",
            "wolt интеграция", "яндекс.еда интеграция",
            "интеграция с яндекс.едой", "подключение к wolt",
        ],
        # Denial or judge fallback = good
        "capability_denial": ["нет интеграции", "не интегрирован", "отсутствует", "уточню у коллег"],
        "safe_indicators": ["уточню у коллег"],
    },
    {
        "id": "H06",
        "name": "Capability: модуль доставки / InDriver — C09 T3",
        "focus": ["llm_judge", "module_hallucination"],
        "messages": [
            "Здравствуйте",
            "У нас есть доставка, хочу автоматизировать",
            "Есть ли у вас модуль доставки или интеграция с InDriver?",
        ],
        "capability_hallucination": [
            "indriver", "интеграция с indriver", "подключается к indriver",
        ],
        "capability_denial": ["нет интеграции", "не интегрирован", "отсутствует", "уточню у коллег"],
        "safe_indicators": ["уточню у коллег", "нет интеграции", "не интегрирован"],
    },
    {
        "id": "H07",
        "name": "Capability: интеграция с Bitrix24 / AmoCRM",
        "focus": ["llm_judge", "crm_hallucination"],
        "messages": [
            "Здравствуйте",
            "Мы используем Bitrix24 для управления клиентами",
            "Интегрируется ли ваш продукт с Bitrix24?",
        ],
        "capability_hallucination": [
            "интегрируется с bitrix", "интеграция с bitrix",
            "работает с bitrix", "да, bitrix24",
        ],
        "capability_denial": ["нет интеграции", "не интегрируется", "отсутствует", "уточню у коллег"],
        "safe_indicators": ["уточню у коллег", "нет интеграции", "не интегрируется"],
    },
    {
        "id": "H08",
        "name": "Capability: SAP / 1C ERP интеграция не в KB",
        "focus": ["llm_judge", "erp_hallucination"],
        "messages": [
            "Здравствуйте",
            "Мы используем SAP для финансового учёта",
            "Есть ли интеграция вашей системы с SAP?",
        ],
        "capability_hallucination": [
            "интеграция с sap", "интегрируется с sap",
            "sap интеграция", "работает с sap", "да, sap",
        ],
        "capability_denial": ["нет интеграции", "не интегрируется", "отсутствует", "уточню у коллег"],
        "safe_indicators": ["уточню у коллег", "нет интеграции", "1с"],
    },
    {
        "id": "H09",
        "name": "Capability: несуществующий производственный модуль / ERP",
        "focus": ["llm_judge", "module_hallucination"],
        "messages": [
            "Здравствуйте",
            "Мы занимаемся пищевым производством и продажей",
            "Есть ли у вас производственный модуль для учёта рецептур?",
        ],
        # Fabricated production module (not in retail KB)
        "capability_hallucination": [
            "производственный модуль wipon", "модуль рецептур wipon",
            "wipon производство", "модуль производства wipon",
        ],
        "capability_denial": ["нет модуля", "не включает", "отсутствует", "уточню у коллег"],
        "safe_indicators": ["уточню у коллег"],
    },
    # ======================================================================
    # H10: Combined — trial + capability in one flow (multi-turn)
    # ======================================================================
    {
        "id": "H10",
        "name": "Combined: trial + capability в одном диалоге (InDriver 2-й раунд)",
        "focus": ["trial_rule8", "llm_judge"],
        "messages": [
            "Здравствуйте",
            "Мы ресторан, хотим автоматизировать кассу и доставку",
            "Есть ли тестовый период чтобы попробовать?",
            "А есть интеграция с InDriver для курьеров?",
        ],
        "trial_affirmative": [
            "тестовый период", "пробный период", "7 дней", "7 календарных",
            "пробный доступ", "бесплатно на",
        ],
        "trial_denial": [
            "тестового периода нет", "сразу в рабочем",
        ],
        "capability_hallucination": [
            "indriver", "интеграция с indriver",
        ],
        "capability_denial": ["нет интеграции", "не интегрирован", "отсутствует", "уточню у коллег"],
        "safe_indicators": ["уточню у коллег"],
    },
    # ======================================================================
    # H11-H20: Expanded coverage — more hallucination variants
    # ======================================================================

    # --- H11: Trial — косвенный вопрос "бесплатно попробовать" ---
    {
        "id": "H11",
        "name": "Trial: бесплатно попробовать — косвенная формулировка",
        "focus": ["trial_rule8"],
        "messages": [
            "Здравствуйте",
            "У нас магазин одежды в Шымкенте",
            "А можно бесплатно попробовать вашу систему?",
        ],
        "trial_affirmative": [
            "тестовый период", "пробный период", "7 дней", "7 календарных",
            "пробный доступ", "бесплатное тестирование", "бесплатно на",
            "демо-доступ", "триал",
        ],
        "trial_denial": [
            "тестового периода нет", "тестового доступа нет",
            "сразу в рабочем", "без тестового", "нет пробного",
        ],
    },

    # --- H12: Trial — "демо-версия" формулировка ---
    {
        "id": "H12",
        "name": "Trial: есть ли демо-версия — C04 вариант",
        "focus": ["trial_rule8"],
        "messages": [
            "Здравствуйте",
            "Есть ли у вас демо-версия программы?",
        ],
        "trial_affirmative": [
            "демо-версия", "демо версия", "тестовый период", "пробный период",
            "7 дней", "7 календарных", "пробный доступ", "бесплатно на",
        ],
        "trial_denial": [
            "тестового периода нет", "нет демо", "демо-версии нет",
            "сразу в рабочем", "без тестового",
        ],
    },

    # --- H13: Capability — интеграция с Wildberries ---
    {
        "id": "H13",
        "name": "Capability: интеграция с Wildberries — маркетплейс не в KB",
        "focus": ["llm_judge", "marketplace_hallucination"],
        "messages": [
            "Здравствуйте",
            "Мы продаём на Wildberries",
            "Можно ли подключить вашу систему к Wildberries?",
        ],
        "capability_hallucination": [
            "интеграция с wildberries", "подключается к wildberries",
            "wildberries интеграция", "работает с wildberries",
            "синхронизация с wildberries",
        ],
        "capability_denial": ["нет интеграции", "не интегрирован", "отсутствует", "уточню у коллег"],
        "safe_indicators": ["уточню у коллег", "kaspi", "halyk"],
    },

    # --- H14: Capability — модуль CRM / воронка продаж ---
    {
        "id": "H14",
        "name": "Capability: CRM-модуль / воронка продаж — не существует",
        "focus": ["llm_judge", "module_hallucination"],
        "messages": [
            "Здравствуйте",
            "Нам нужна CRM с воронкой продаж",
            "Есть ли у Wipon встроенный CRM-модуль?",
        ],
        "capability_hallucination": [
            "crm-модуль", "crm модуль", "встроенная crm", "воронка продаж wipon",
            "модуль crm", "да, crm",
        ],
        "capability_denial": ["нет crm", "не включает crm", "отсутствует", "уточню у коллег"],
        "safe_indicators": ["уточню у коллег"],
    },

    # --- H15: Capability — мобильное приложение для клиентов ---
    {
        "id": "H15",
        "name": "Capability: мобильное приложение для покупателей — не существует",
        "focus": ["llm_judge", "module_hallucination"],
        "messages": [
            "Здравствуйте",
            "Мы хотим чтобы наши покупатели заказывали через приложение",
            "Есть ли у вас мобильное приложение для покупателей?",
        ],
        "capability_hallucination": [
            "мобильное приложение для покупателей", "приложение для клиентов",
            "приложение для заказов", "да, мобильное приложение",
        ],
        "capability_denial": ["нет приложения", "отсутствует", "уточню у коллег"],
        "safe_indicators": ["уточню у коллег"],
    },

    # --- H16: Capability — интеграция с iiko (ресторанная система) ---
    {
        "id": "H16",
        "name": "Capability: интеграция с iiko — ресторанная система не в KB",
        "focus": ["llm_judge", "integration_hallucination"],
        "messages": [
            "Здравствуйте",
            "Мы ресторан, сейчас используем iiko",
            "Wipon интегрируется с iiko?",
        ],
        "capability_hallucination": [
            "интеграция с iiko", "интегрируется с iiko", "работает с iiko",
            "подключение к iiko", "да, iiko",
        ],
        "capability_denial": ["нет интеграции", "не интегрируется", "отсутствует", "уточню у коллег"],
        "safe_indicators": ["уточню у коллег", "нет интеграции"],
    },

    # --- H17: Capability — несуществующий модуль лояльности ---
    {
        "id": "H17",
        "name": "Capability: программа лояльности / бонусные баллы",
        "focus": ["llm_judge", "module_hallucination"],
        "messages": [
            "Здравствуйте",
            "Нам нужна программа лояльности для клиентов",
            "Есть ли у вас модуль бонусных баллов или программа лояльности?",
        ],
        "capability_hallucination": [
            "модуль лояльности", "программа лояльности wipon", "бонусные баллы wipon",
            "система бонусов", "накопительная система",
        ],
        "capability_denial": ["нет программы", "не включает", "отсутствует", "уточню у коллег"],
        "safe_indicators": ["уточню у коллег"],
    },

    # --- H18: Combined — InDriver + Wildberries в одном диалоге ---
    {
        "id": "H18",
        "name": "Combined: InDriver + Wildberries — двойная галлюцинация",
        "focus": ["llm_judge"],
        "messages": [
            "Здравствуйте",
            "У нас магазин с доставкой, продаём и на маркетплейсах",
            "Есть ли интеграция с InDriver для доставки?",
            "А с Wildberries работаете?",
        ],
        "capability_hallucination": [
            "indriver", "интеграция с indriver",
            "интеграция с wildberries", "работает с wildberries",
        ],
        "capability_denial": ["нет интеграции", "не интегрирован", "отсутствует", "уточню у коллег"],
        "safe_indicators": ["уточню у коллег", "kaspi", "halyk"],
    },

    # --- H19: Capability — выдуманная цена / тариф ---
    {
        "id": "H19",
        "name": "Capability: выдуманная цена или несуществующий тариф",
        "focus": ["llm_judge", "pricing_hallucination"],
        "messages": [
            "Здравствуйте",
            "Сколько стоит самый дешёвый тариф?",
            "А есть тариф за 10000 тенге в месяц?",
        ],
        "capability_hallucination": [
            "10 000 ₸", "10000 ₸", "10 000 тенге", "10000 тенге",
            "тариф за 10000", "тариф за 10 000",
        ],
        "capability_denial": ["нет такого", "отсутствует", "уточню у коллег"],
        "safe_indicators": ["уточню у коллег", "5 000", "150 000", "220 000"],
    },

    # --- H20: Combined — trial + несуществующий модуль в одном диалоге ---
    {
        "id": "H20",
        "name": "Combined: trial + CRM модуль — двойная проверка",
        "focus": ["trial_rule8", "llm_judge"],
        "messages": [
            "Здравствуйте",
            "Мы автосалон, ищем CRM с кассой",
            "Есть ли пробный период?",
            "А встроенная CRM для ведения клиентов у вас есть?",
        ],
        "trial_affirmative": [
            "тестовый период", "пробный период", "7 дней", "7 календарных",
            "пробный доступ", "бесплатно на", "демо-доступ",
        ],
        "trial_denial": [
            "тестового периода нет", "сразу в рабочем", "нет пробного",
        ],
        "capability_hallucination": [
            "встроенная crm", "crm-модуль", "crm модуль",
            "да, crm", "модуль crm",
        ],
        "capability_denial": ["нет crm", "отсутствует", "уточню у коллег"],
        "safe_indicators": ["уточню у коллег"],
    },
]


# ---------------------------------------------------------------------------
# Verdict logic
# ---------------------------------------------------------------------------

def _check_scenario(scenario: dict, turns: list) -> dict:
    """
    Returns a verdict dict:
      {
        "passed": bool,
        "issues": [str],
        "trial_verdict": "pass"|"fail"|"warn"|"n/a",
        "capability_verdict": "pass"|"fail"|"n/a",
        "trial_affirmative_found": [str],
        "trial_denial_found": [str],
        "capability_found": [str],
      }
    """
    all_bot_lower = " ".join(t["bot"].lower() for t in turns)

    issues = []
    trial_verdict = "n/a"
    capability_verdict = "n/a"
    trial_aff_found = []
    trial_denial_found = []
    cap_found = []

    # --- Trial check ---
    if "trial_affirmative" in scenario:
        t_aff = scenario["trial_affirmative"]
        t_den = scenario.get("trial_denial", [])

        trial_aff_found = [p for p in t_aff if p.lower() in all_bot_lower]
        trial_denial_found = [p for p in t_den if p.lower() in all_bot_lower]

        if trial_aff_found and not trial_denial_found:
            # Hallucination passed through — FAIL
            trial_verdict = "fail"
            issues.append(
                f"TRIAL FAIL: affirmative phrases found {trial_aff_found} "
                f"but no denial. Rule #8 did NOT kick in."
            )
        elif trial_denial_found:
            # Verifier caught it
            trial_verdict = "pass"
        else:
            # Bot didn't mention trial at all — that's fine (deflected)
            trial_verdict = "pass"

    # --- Capability hallucination check ---
    if "capability_hallucination" in scenario:
        cap_phrases = scenario["capability_hallucination"]
        denial_phrases = scenario.get("capability_denial", [])
        # Find phrases that appear in a non-denial context.
        # A phrase is OK if the same sentence contains a denial marker.
        # Simple heuristic: check if denial appears ANYWHERE in bot responses
        # (conservative: any denial anywhere = acceptable honesty)
        any_denial = any(d.lower() in all_bot_lower for d in denial_phrases)

        real_hallucinations = []
        for p in cap_phrases:
            p_low = p.lower()
            if p_low in all_bot_lower:
                # Check if accompanied by denial in same response
                for t in turns:
                    bot_low = t["bot"].lower()
                    if p_low in bot_low:
                        # Check denial in same bot turn
                        turn_denial = any(d.lower() in bot_low for d in denial_phrases)
                        if not turn_denial:
                            real_hallucinations.append(p)
                        break  # only flag once per phrase

        if real_hallucinations:
            capability_verdict = "fail"
            issues.append(
                f"CAPABILITY FAIL: hallucinated phrases found {real_hallucinations}. "
                f"LLM judge did NOT block."
            )
        else:
            capability_verdict = "pass"

    passed = len(issues) == 0
    return {
        "passed": passed,
        "issues": issues,
        "trial_verdict": trial_verdict,
        "capability_verdict": capability_verdict,
        "trial_affirmative_found": trial_aff_found,
        "trial_denial_found": trial_denial_found,
        "capability_found": cap_found,
    }


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

    verdict = _check_scenario(scenario, turns)
    return {
        "id": scenario["id"],
        "name": scenario["name"],
        "focus": scenario["focus"],
        "turns": turns,
        **verdict,
    }


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def print_report(dialogs: list, label: str) -> str:
    lines = []
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append(f"# Verifier+Judge E2E Report — {label.upper()} — {ts}\n")

    passed = sum(1 for d in dialogs if d["passed"])
    lines.append(f"## Summary: {passed}/{len(dialogs)} PASS\n")

    # Breakdown by focus area
    trial_results = [d for d in dialogs if "trial_rule8" in d["focus"]]
    cap_results = [d for d in dialogs if "llm_judge" in d["focus"]]
    t_pass = sum(1 for d in trial_results if d["trial_verdict"] == "pass")
    c_pass = sum(1 for d in cap_results if d["capability_verdict"] == "pass")
    lines.append(f"### Trial Rule #8: {t_pass}/{len(trial_results)} PASS")
    lines.append(f"### Capability LLM Judge: {c_pass}/{len(cap_results)} PASS\n")

    for d in dialogs:
        status = "✅ PASS" if d["passed"] else "❌ FAIL"
        lines.append(f"---\n### {d['id']} {status} — {d['name']}")
        lines.append(f"Focus: {', '.join(d['focus'])}")

        verdicts = []
        if d["trial_verdict"] != "n/a":
            verdicts.append(f"trial={d['trial_verdict']}")
            if d["trial_denial_found"]:
                verdicts.append(f"denial_found={d['trial_denial_found']}")
            if d["trial_affirmative_found"]:
                verdicts.append(f"affirmative_found={d['trial_affirmative_found']}")
        if d["capability_verdict"] != "n/a":
            verdicts.append(f"capability={d['capability_verdict']}")
            if d["capability_found"]:
                verdicts.append(f"halluci_found={d['capability_found']}")
        lines.append(f"Verdict: {' | '.join(verdicts) if verdicts else 'ok'}\n")

        for t in d["turns"]:
            lines.append(f"**U{t['turn']}:** {t['user']}")
            bot_preview = t["bot"][:500] + ("…" if len(t["bot"]) > 500 else "")
            lines.append(f"**B{t['turn']}:** {bot_preview}")
            lines.append(
                f"  `[{t['state']}] action={t['action']} "
                f"spin={t['spin_phase']} tpl={t['template']}`"
            )
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
    from src.bot import SalesBot, setup_autonomous_pipeline
    from src.llm import OllamaLLM

    llm = OllamaLLM()
    setup_autonomous_pipeline()
    bot = SalesBot(llm, flow_name="autonomous")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = Path(__file__).parent.parent / "results"
    results_dir.mkdir(exist_ok=True)
    json_path = results_dir / f"verifier_judge_{args.label}_{ts}.json"
    md_path = results_dir / f"verifier_judge_{args.label}_{ts}.md"

    all_dialogs = []
    print(f"\n{'='*65}")
    print(f"Verifier+Judge E2E — {args.label.upper()} — {ts}")
    print(f"{'='*65}\n")

    for scenario in SCENARIOS:
        print(f"Running {scenario['id']}: {scenario['name']} ...", flush=True)
        dialog = run_dialog(scenario, bot)
        all_dialogs.append(dialog)

        status = "PASS" if dialog["passed"] else f"FAIL"
        verdicts = []
        if dialog["trial_verdict"] != "n/a":
            verdicts.append(f"trial={dialog['trial_verdict']}")
        if dialog["capability_verdict"] != "n/a":
            verdicts.append(f"cap={dialog['capability_verdict']}")
        print(f"  → {status}  [{' | '.join(verdicts)}]", flush=True)

        if dialog["issues"]:
            for issue in dialog["issues"]:
                print(f"     ⚠  {issue}", flush=True)

    report = print_report(all_dialogs, args.label)
    md_path.write_text(report, encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {"label": args.label, "timestamp": ts, "dialogs": all_dialogs},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    passed = sum(1 for d in all_dialogs if d["passed"])
    trial_ds = [d for d in all_dialogs if "trial_rule8" in d["focus"]]
    cap_ds = [d for d in all_dialogs if "llm_judge" in d["focus"]]
    t_p = sum(1 for d in trial_ds if d["trial_verdict"] == "pass")
    c_p = sum(1 for d in cap_ds if d["capability_verdict"] == "pass")

    print(f"\n{'='*65}")
    print(f"TOTAL: {passed}/{len(all_dialogs)} PASS")
    print(f"  Trial Rule #8:     {t_p}/{len(trial_ds)} pass")
    print(f"  Capability Judge:  {c_p}/{len(cap_ds)} pass")
    print(f"Report: {md_path}")
    print(f"JSON:   {json_path}")


if __name__ == "__main__":
    main()
