"""
BUG4 Stress Test — жёсткая проверка трёх изменённых мест:

  1. {retrieved_facts} перед {history} в autonomous_respond
     → KB grounding: бот использует конкретные факты, а не галлюцинирует
     → do_not_ask в конце промпта: бот не переспрашивает известное

  2. {retrieved_facts} перед {history} в continue_current_goal
     → то же, в шаблоне для продолжения цели

  3. Убран дублирующий {do_not_ask} из answer_with_pricing
     → при ценовых вопросах нет двойного "не делай X"

Жёсткость: многоходовые диалоги, противоречивые клиенты,
угловые случаи — всё что могло регрессировать.

Usage:
    python -m scripts.bug4_stress 2>/dev/null
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Сценарии разбиты по трём областям изменений
# ---------------------------------------------------------------------------

SCENARIOS = [

    # =========================================================
    # БЛОК 1: KB GROUNDING (retrieved_facts до history)
    # Бот должен использовать точные факты из KB, не придумывать
    # =========================================================

    {
        "id": "G01",
        "name": "Точная цена Mini не придумана",
        "area": "kb_grounding",
        "checks": {
            "must_contain_any": ["5 000"],
            "must_not_contain": ["уточню", "уточним", "свяжитесь", "не знаю"],
        },
        "messages": [
            "Здравствуйте",
            "Один небольшой магазин",
            "Сколько Mini стоит в месяц?",
        ],
    },
    {
        "id": "G02",
        "name": "Точная цена Lite не придумана",
        "area": "kb_grounding",
        "checks": {
            "must_contain_any": ["150 000", "150000"],
            "must_not_contain": ["уточню", "не знаю"],
        },
        "messages": [
            "Здравствуйте",
            "Два магазина, хотим интеграцию с Kaspi",
            "Сколько стоит Lite?",
        ],
    },
    {
        "id": "G03",
        "name": "Standard: только Lite/Standard/Pro интегрируются с Kaspi (не Mini)",
        "area": "kb_grounding",
        "checks": {
            "must_not_contain": ["mini интегрируется с kaspi", "mini поддерживает kaspi",
                                  "любой тариф", "все тарифы поддерживают kaspi"],
        },
        "messages": [
            "Здравствуйте",
            "Продуктовый магазин, оплата через Kaspi важна",
            "Mini подходит если нужен Kaspi?",
        ],
    },
    {
        "id": "G04",
        "name": "Функции Standard: развёрнутый ответ из KB, не одна фраза",
        "area": "kb_grounding",
        "checks": {
            "must_contain_any": ["касс", "фискал", "интеграц", "склад", "номенклатур"],
            "must_not_contain": ["уточните", "расскажите подробнее о задачах"],
        },
        "messages": [
            "Здравствуйте",
            "Сеть из трёх магазинов одежды",
            "Подробно: что входит в Standard?",
        ],
    },
    {
        "id": "G05",
        "name": "Pro: функции не приписываются Mini или Lite",
        "area": "kb_grounding",
        "checks": {
            "must_contain_any": ["Pro", "про"],
            "must_not_contain": ["mini включает", "lite включает", "уточню"],
        },
        "messages": [
            "Здравствуйте",
            "Крупная сеть 10 точек",
            "Что даёт Pro сверх Standard?",
        ],
    },
    {
        "id": "G06",
        "name": "Цена не считается (5 точек × 5000 ≠ 25000): нет самодельных расчётов",
        "area": "kb_grounding",
        "checks": {
            "must_not_contain": ["25 000", "25000", "150 000 × 5", "умножить"],
        },
        "messages": [
            "Здравствуйте",
            "У меня 5 небольших точек",
            "Сколько будет стоить Mini для 5 точек?",
        ],
    },
    {
        "id": "G07",
        "name": "Нет данных в KB → честный ответ, без придумки",
        "area": "kb_grounding",
        "checks": {
            "must_not_contain": ["интеграция с 1с стоит", "1с стоит", "настройка 1с — 10"],
        },
        "messages": [
            "Здравствуйте",
            "Магазин на 1С",
            "Сколько стоит перенос базы данных с 1С?",
        ],
    },

    # =========================================================
    # БЛОК 2: DO_NOT_ASK COMPLIANCE (инструкции в конце промпта)
    # Бот НЕ должен переспрашивать то, что уже известно
    # =========================================================

    {
        "id": "D01",
        "name": "Бизнес-тип известен → не переспрашивается ни разу за диалог",
        "area": "do_not_ask",
        "checks": {
            "must_not_contain": ["какой у вас бизнес", "что за бизнес", "чем занимаетесь",
                                  "расскажите о вашем бизнесе", "какой тип бизнеса",
                                  "расскажите подробнее о компании"],
        },
        "messages": [
            "Здравствуйте",
            "Цветочный магазин, 2 точки в Алматы",
            "Интересует автоматизация",
            "Что по тарифам?",
            "А что с поддержкой?",
            "Сколько стоит?",
        ],
    },
    {
        "id": "D02",
        "name": "Количество точек известно → не переспрашивается",
        "area": "do_not_ask",
        "checks": {
            "must_not_contain": ["сколько у вас точек", "сколько торговых точек",
                                  "количество точек", "сколько магазинов"],
        },
        "messages": [
            "Здравствуйте",
            "У меня сеть из 4 магазинов в Нур-Султане",
            "Какой тариф лучше для 4 точек?",
            "А поддержка как работает?",
            "Можно ли добавить точку потом?",
        ],
    },
    {
        "id": "D03",
        "name": "Имя дано → не спрашивается повторно",
        "area": "do_not_ask",
        "checks": {
            "must_not_contain": ["как вас зовут", "как к вам обращаться",
                                  "представьтесь", "ваше имя"],
        },
        "messages": [
            "Здравствуйте, я Динара",
            "Кафе в Шымкенте",
            "Расскажите про тарифы",
            "А Dinara сможет разобраться без обучения?",
            "Как долго длится внедрение?",
        ],
    },
    {
        "id": "D04",
        "name": "Боль озвучена → бот не просит 'расскажите о проблеме' снова",
        "area": "do_not_ask",
        "checks": {
            "must_not_contain": ["расскажите о ваших проблемах", "с чем именно возникают сложности",
                                  "что именно не устраивает", "расскажите подробнее о трудностях"],
        },
        "messages": [
            "Здравствуйте",
            "Аптека, 3 точки. Главная боль — расхождения в остатках между точками",
            "Это решаемо?",
            "Сколько стоит?",
            "Есть ли тестовый период?",
        ],
    },
    {
        "id": "D05",
        "name": "Контакт дан → не переспрашивается в closing",
        "area": "do_not_ask",
        "checks": {
            "must_not_contain": ["ваш телефон", "оставьте номер", "как с вами связаться",
                                  "укажите контакт"],
        },
        "messages": [
            "Здравствуйте",
            "Магазин электроники, Алматы, одна точка",
            "Хочу подключиться к Lite",
            "Мой номер: +77771234567",
            "Когда свяжутся?",
        ],
    },
    {
        "id": "D06",
        "name": "Длинный диалог 9 ходов: do_not_ask держится до конца",
        "area": "do_not_ask",
        "checks": {
            "must_not_contain": ["какой у вас бизнес", "сколько точек",
                                  "расскажите о компании", "чем занимаетесь"],
        },
        "messages": [
            "Здравствуйте",
            "Ресторан быстрого питания, 2 точки в Алматы",
            "Проблема с учётом — не знаем что списывать",
            "Какой тариф подойдёт?",
            "А Kaspi QR поддерживается?",
            "Что по оборудованию?",
            "Как долго внедрение?",
            "Есть рассрочка?",
            "Хорошо, хочу оформить",
        ],
    },

    # =========================================================
    # БЛОК 3: ANSWER_WITH_PRICING (убран дублирующий do_not_ask)
    # Бот всегда называет цену ПЕРВЫМ делом, не задаёт вопросы без цены
    # =========================================================

    {
        "id": "P01",
        "name": "Ценовой вопрос → цена в ответе, не 'расскажите о компании'",
        "area": "answer_with_pricing",
        "checks": {
            "must_contain_any": ["₸", "тенге", "тариф"],
            "must_not_contain": ["расскажите о компании", "сначала расскажите",
                                  "для начала уточните"],
        },
        "messages": [
            "Здравствуйте",
            "Сколько стоит ваш продукт?",
        ],
    },
    {
        "id": "P02",
        "name": "Цена + follow-up: бот отвечает на цену И задаёт один вопрос",
        "area": "answer_with_pricing",
        "checks": {
            "must_contain_any": ["₸", "тенге", "5 000", "150 000"],
            "must_not_contain": ["цена зависит от многих факторов",
                                  "сначала расскажите", "сколько у вас сотрудников"],
        },
        "messages": [
            "Здравствуйте",
            "Магазин косметики",
            "Какие цены?",
        ],
    },
    {
        "id": "P03",
        "name": "Нет двойного запрета: бот не говорит 'не могу' дважды подряд",
        "area": "answer_with_pricing",
        "checks": {
            "must_contain_any": ["₸", "тенге"],
            "must_not_contain": ["не могу ответить без", "не могу назвать цену",
                                  "сначала нужно понять"],
        },
        "messages": [
            "Здравствуйте",
            "Маленький магазинчик, 1 касса",
            "Цены?",
        ],
    },
    {
        "id": "P04",
        "name": "Pricing при наличии клиентского контекста: учитывает то что знает",
        "area": "answer_with_pricing",
        "checks": {
            "must_contain_any": ["₸", "тариф", "Mini", "Lite"],
            "must_not_contain": ["расскажите сколько у вас точек",
                                  "для начала расскажите о компании"],
        },
        "messages": [
            "Здравствуйте",
            "Небольшое кафе, 1 касса, Алматы",
            "Итак, сколько будет стоить?",
        ],
    },

    # =========================================================
    # БЛОК 4: РЕГРЕССИЯ — то что работало до, должно работать после
    # =========================================================

    {
        "id": "R01",
        "name": "Регрессия: greeting работает корректно",
        "area": "regression",
        "checks": {
            "must_contain_any": ["Айбота", "консультант", "Wipon"],
            "must_not_contain": ["ошибка", "error", "traceback"],
        },
        "messages": [
            "Привет",
        ],
    },
    {
        "id": "R02",
        "name": "Регрессия: Казах-спикер — бот отвечает по-казахски",
        "area": "regression",
        "checks": {
            "must_contain_any": ["сәлем", "рахмет", "Айбота", "Wipon",
                                  "мен", "сіз", "қош"],
        },
        "messages": [
            "Сәлем",
            "Менің дүкенім бар, Алматыда",
        ],
    },
    {
        "id": "R03",
        "name": "Регрессия: escalation → коллега позвонит (не 'менеджер')",
        "area": "regression",
        "checks": {
            "must_not_contain": ["менеджер свяжется", "наш менеджер позвонит"],
            "must_contain_any": ["коллега", "позвон", "свяж"],
        },
        "messages": [
            "Здравствуйте",
            "Хочу поговорить с живым человеком",
        ],
    },
    {
        "id": "R04",
        "name": "Регрессия: objection 'не сейчас' — бот не давит, мягко",
        "area": "regression",
        "checks": {
            "must_not_contain": ["вы должны", "обязательно купите", "срочно"],
        },
        "messages": [
            "Здравствуйте",
            "Магазин одежды",
            "Пока не готов, вернусь позже",
        ],
    },
    {
        "id": "R05",
        "name": "Регрессия: бот не придумывает demo/тест/trial",
        "area": "regression",
        "checks": {
            "must_not_contain": ["тестовый период", "бесплатный период", "демо-доступ",
                                  "пробный период", "7 дней бесплатно"],
        },
        "messages": [
            "Здравствуйте",
            "Можно ли попробовать перед покупкой?",
        ],
    },
]


# ---------------------------------------------------------------------------
# Check runner
# ---------------------------------------------------------------------------

def run_checks(scenario: dict, turns: list) -> list:
    issues = []
    checks = scenario.get("checks", {})
    all_bot = " ".join(t["bot"] for t in turns)
    all_bot_lower = all_bot.lower()

    must_any = checks.get("must_contain_any", [])
    if must_any and not any(p.lower() in all_bot_lower for p in must_any):
        issues.append(f"FAIL must_contain_any: none of {must_any} found in bot responses")

    for phrase in checks.get("must_not_contain", []):
        if phrase.lower() in all_bot_lower:
            for t in turns:
                if phrase.lower() in t["bot"].lower():
                    issues.append(
                        f"FAIL must_not_contain: '{phrase}' at turn {t['turn']}: "
                        f"«{t['bot'][:150]}»"
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
        "area": scenario["area"],
        "turns": turns,
        "issues": issues,
        "passed": len(issues) == 0,
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report(dialogs: list) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"# BUG4 Stress Test — {ts}\n"]

    # Per-area summary
    areas = {}
    for d in dialogs:
        a = d["area"]
        areas.setdefault(a, {"pass": 0, "fail": 0})
        if d["passed"]:
            areas[a]["pass"] += 1
        else:
            areas[a]["fail"] += 1

    total_pass = sum(d["passed"] for d in dialogs)
    lines.append(f"## Total: {total_pass}/{len(dialogs)} PASS\n")
    lines.append("| Area | PASS | FAIL |")
    lines.append("|------|------|------|")
    for area, counts in areas.items():
        lines.append(f"| {area} | {counts['pass']} | {counts['fail']} |")
    lines.append("")

    for d in dialogs:
        status = "✅" if d["passed"] else "❌"
        lines.append(f"---\n### {d['id']} {status} [{d['area']}] — {d['name']}")
        for t in d["turns"]:
            lines.append(f"**U{t['turn']}:** {t['user']}")
            preview = t["bot"][:400] + ("…" if len(t["bot"]) > 400 else "")
            lines.append(f"**B{t['turn']}:** {preview}")
            lines.append(f"  `[{t['state']}] {t['action']} spin={t['spin_phase']} tpl={t['template']}`")
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
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.bot import SalesBot, setup_autonomous_pipeline
    from src.llm import OllamaLLM

    llm = OllamaLLM()
    setup_autonomous_pipeline()
    bot = SalesBot(llm, flow_name="autonomous")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = Path(__file__).parent.parent / "results"
    results_dir.mkdir(exist_ok=True)
    json_path = results_dir / f"bug4_stress_{ts}.json"
    md_path = results_dir / f"bug4_stress_{ts}.md"

    all_dialogs = []
    area_stats: dict = {}

    for scenario in SCENARIOS:
        print(f"  {scenario['id']} [{scenario['area']}] {scenario['name']} ...", flush=True)
        d = run_dialog(scenario, bot)
        all_dialogs.append(d)

        a = scenario["area"]
        area_stats.setdefault(a, {"pass": 0, "fail": 0})
        if d["passed"]:
            area_stats[a]["pass"] += 1
            print(f"    → PASS", flush=True)
        else:
            area_stats[a]["fail"] += 1
            print(f"    → FAIL", flush=True)
            for issue in d["issues"]:
                print(f"       {issue}", flush=True)

    report = print_report(all_dialogs)
    md_path.write_text(report, encoding="utf-8")
    json_path.write_text(
        json.dumps({"timestamp": ts, "dialogs": all_dialogs}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    total_pass = sum(d["passed"] for d in all_dialogs)
    print(f"\n{'='*60}")
    print(f"RESULT: {total_pass}/{len(all_dialogs)} PASS")
    print()
    for area, counts in area_stats.items():
        total = counts["pass"] + counts["fail"]
        print(f"  {area}: {counts['pass']}/{total}")
    print(f"\nReport: {md_path}")


if __name__ == "__main__":
    main()
