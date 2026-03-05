#!/usr/bin/env python3
"""
DISAMBIGUATION E2E — 10 targeted scenarios.

Фокус: rule-based FactDisambiguator перехватывает ответ LLM и вставляет жёсткое
"Уточните, пожалуйста, что вы имеете в виду под «Pro»:
 1) Тариф Pro
 2) Комплект Pro
 Ответьте номером 1-3..."
— часто ложно, игнорируя контекст диалога.

Три группы:
  GROUP A (S01–S06): Контекст ЯСЕН — disambiguation НЕ нужен. Жёсткий формат = FAIL.
  GROUP B (S07–S08): Контекст НЕЯСЕН — disambiguation нужен, но ОРГАНИЧНО (не жёсткий формат).
  GROUP C (S09–S10): Крайние случаи (closing state, повторное уточнение).

Проверяемый патч:
  response_fact_disambiguation: false  →  LLM handles disambiguation via rule 15.

Запуск:
    python -m scripts.disambiguation_e2e 2>/dev/null
"""

import sys
import re
import json
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.bot import SalesBot, setup_autonomous_pipeline
from src.llm import OllamaLLM
from src.feature_flags import flags

# ---------------------------------------------------------------------------
# Паттерны детекции
# ---------------------------------------------------------------------------

# Жёсткий rule-based формат disambiguator
RIGID_DISAMBIG = re.compile(
    r'Уточните,?\s*пожалуйста,?\s*что\s+вы\s+имеете\s+в\s+виду',
    re.IGNORECASE,
)

# Нумерованный список "1) ... 2) ..."
NUMBERED_LIST = re.compile(
    r'(?m)^\s*[1-3][\)\.\-]\s+(?:Тариф|Комплект|Модуль)',
    re.IGNORECASE,
)

# "Ответьте номером 1-3"
ANSWER_BY_NUMBER = re.compile(
    r'Ответьте\s+номером',
    re.IGNORECASE,
)

# Органичное уточнение (LLM спрашивает мягко)
ORGANIC_CLARIFICATION = re.compile(
    r'(?:что\s+(?:именно|конкретно)|вас\s+интересует|'
    r'имеете\s+в\s+виду|уточните|какой\s+(?:именно|вариант))',
    re.IGNORECASE,
)

# Тарифы в ответе
TARIFF_MENTION = re.compile(
    r'(?:Mini|Lite|Standard|Pro|ТИС'
    r'|5\s*000\s*[₸Т]|5000\s*[₸Т]'
    r'|150\s*000\s*[₸Т]|150000\s*[₸Т]'
    r'|220\s*000\s*[₸Т]|220000\s*[₸Т]'
    r'|500\s*000\s*[₸Т]|500000\s*[₸Т]'
    r'|тари[фв])',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Сценарии
# ---------------------------------------------------------------------------
SCENARIOS = [

    # ═══════════════════════════════════════════════════
    # GROUP A: Контекст ЯСЕН — disambiguation НЕ нужен
    # ═══════════════════════════════════════════════════

    {
        "id": "S01",
        "group": "A",
        "name": "«Расскажите про тариф Pro» — явное слово 'тариф'",
        "desc": (
            "Клиент прямо говорит «тариф Pro». Disambiguator может сработать "
            "т.к. в retrieved_facts есть и тариф и комплект Pro. "
            "Но контекст однозначен — тариф."
        ),
        "expect_rigid": False,
        "msgs": [
            "Здравствуйте, у меня 4 магазина электроники",
            "Расскажите про тариф Pro — нам подойдёт?",
            "500 тысяч в год — а помесячная оплата есть?",
            "Понял. Давайте оформим. Телефон: 87715551234",
        ],
    },

    {
        "id": "S02",
        "group": "A",
        "name": "«Сколько стоит Lite?» — ценовой контекст = тариф",
        "desc": (
            "Слово 'стоит' + 'Lite' — однозначно ценовой запрос о тарифе. "
            "Disambiguator видит Lite тариф + Lite комплект в фактах и может сработать. "
            "Но ценовой контекст делает тариф очевидным."
        ),
        "expect_rigid": False,
        "msgs": [
            "Добрый день, у меня 1 точка продаж в Костанае",
            "Сколько стоит Lite?",
            "А Mini за 5000 в месяц — это дешевле?",
            "Lite за 150 тысяч в год выгоднее. Берём. Почта: shop@mail.kz",
        ],
    },

    {
        "id": "S03",
        "group": "A",
        "name": "Сравнение «Mini или Standard» — сравнивают тарифы",
        "desc": (
            "Клиент сравнивает два тарифа. Disambiguator может сработать на обоих "
            "(Mini тариф/комплект + Standard тариф/комплект). "
            "Но никто не сравнивает комплекты так — только тарифы."
        ),
        "expect_rigid": False,
        "msgs": [
            "Привет, мы открываем магазин сувениров в Алматы",
            "Что лучше — Mini или Standard для одной кассы?",
            "5000 в месяц против 220 000 в год — Standard выгоднее?",
            "Хорошо, возьмём Standard. Как подключиться? Мой номер 87013456789",
        ],
    },

    {
        "id": "S04",
        "group": "A",
        "name": "«Pro подходит?» после обсуждения бизнеса — тариф из контекста",
        "desc": (
            "Клиент описал бизнес (5 точек), обсудил потребности. "
            "Когда спрашивает 'Pro подойдёт?' — это про тариф, ясно из контекста."
        ),
        "expect_rigid": False,
        "msgs": [
            "Здравствуйте, у нас 5 продуктовых магазинов в Астане",
            "Нужен складской учёт и аналитика продаж по каждой точке",
            "Значит Pro подойдёт? Сколько платить в год?",
            "500 тысяч за все 5 — нормально. Оформляем. 87071112233",
        ],
    },

    {
        "id": "S05",
        "group": "A",
        "name": "«Что входит в Standard?» после ценового вопроса — функционал тарифа",
        "desc": (
            "Клиент уже спрашивал про цены, теперь просит перечислить "
            "что входит в Standard. Контекст — тарифный."
        ),
        "expect_rigid": False,
        "msgs": [
            "Добрый день, 2 точки обувного магазина",
            "Какие у вас тарифы?",
            "Что входит в Standard? Какие функции?",
            "А складской учёт есть в Standard?",
            "Подходит. Давайте Standard. Email: shoes@company.kz",
        ],
    },

    {
        "id": "S06",
        "group": "A",
        "name": "Казахский: «Pro қанша тұрады?» — ценовой вопрос на казахском",
        "desc": (
            "Клиент спрашивает про Pro на казахском ('сколько стоит Pro?'). "
            "Disambiguator не учитывает казахский контекст и может сработать."
        ),
        "expect_rigid": False,
        "msgs": [
            "Сәлем, менде 3 дүкен бар Шымкентте",
            "Pro тарифі қанша тұрады?",
            "500 мың теңге жылына — жақсы. Оформляймыз",
            "Байланыс: 87751234567",
        ],
    },

    # ═══════════════════════════════════════════════════
    # GROUP B: Контекст НЕЯСЕН — уточнение нужно, но ОРГАНИЧНО
    # ═══════════════════════════════════════════════════

    {
        "id": "S07",
        "group": "B",
        "name": "«Расскажите про Pro» без контекста — настоящая неоднозначность",
        "desc": (
            "Клиент не дал никакого контекста — ни ценового, ни оборудовательного. "
            "'Расскажите про Pro' реально неоднозначно. "
            "LLM должен уточнить ОРГАНИЧНО, не жёстким списком 1) 2) 3)."
        ),
        "expect_rigid": False,  # жёсткий формат = FAIL даже тут
        "expect_clarification": True,  # органичное уточнение = бонус
        "msgs": [
            "Здравствуйте",
            "Расскажите про Pro",
            "Тариф интересует, сколько стоит?",
            "Понял, 500 тысяч в год. Подходит. 87019998877",
        ],
    },

    {
        "id": "S08",
        "group": "B",
        "name": "«Что есть в Mini?» без контекста — тариф или комплект?",
        "desc": (
            "Клиент спрашивает 'что есть в Mini' — может быть тариф (функции) "
            "или комплект (оборудование). LLM должен ответить органично."
        ),
        "expect_rigid": False,
        "expect_clarification": True,
        "msgs": [
            "Привет, только открываюсь",
            "Что есть в Mini?",
            "Меня тариф интересует — какие функции в Mini?",
            "Годится, 5000 в месяц устроит. Как оплатить? 87025554433",
        ],
    },

    # ═══════════════════════════════════════════════════
    # GROUP C: Крайние случаи
    # ═══════════════════════════════════════════════════

    {
        "id": "S09",
        "group": "C",
        "name": "Closing state: клиент уточняет Pro, disambiguator блокирует закрытие",
        "desc": (
            "Клиент в closing даёт контакт + уточняет про Pro. "
            "Disambiguator может перехватить и сломать закрытие сделки. "
            "Жёсткое уточнение в closing — категорически неприемлемо."
        ),
        "expect_rigid": False,
        "msgs": [
            "Здравствуйте, у меня 4 магазина косметики в Алматы",
            "Нужна автоматизация. Какой тариф подойдёт?",
            "Pro за 500 тысяч — подходит. Давайте оформим",
            "Телефон: 87771234567. Кстати, а Pro — это с обновлениями?",
            "Отлично. Жду звонка",
        ],
    },

    {
        "id": "S10",
        "group": "C",
        "name": "Повторный вопрос: disambiguator уже спросил, клиент ответил → спрашивает снова",
        "desc": (
            "Клиент ответил на уточнение (сказал 'тариф'). "
            "Через пару ходов спрашивает ещё раз про Pro. "
            "Disambiguator может спросить СНОВА. Повторное уточнение = FAIL."
        ),
        "expect_rigid": False,
        "msgs": [
            "Привет, у меня бутик одежды",
            "Расскажите про Pro",
            "Тариф",
            "А Pro подключается сразу на все мои 3 точки?",
            "Отлично. Сколько в год? Оформляйте",
            "87015556677",
        ],
    },
]

DIVIDER = "─" * 80


# ---------------------------------------------------------------------------
# Проверка одного хода
# ---------------------------------------------------------------------------
def check_turn(bot_text: str, turn_num: int, scenario: dict) -> dict:
    has_rigid = bool(RIGID_DISAMBIG.search(bot_text))
    has_numbered = bool(NUMBERED_LIST.search(bot_text))
    has_answer_num = bool(ANSWER_BY_NUMBER.search(bot_text))
    has_organic = bool(ORGANIC_CLARIFICATION.search(bot_text))
    has_tariff = bool(TARIFF_MENTION.search(bot_text))

    # Жёсткий формат = rigid + (numbered или answer_by_number)
    is_rigid_format = has_rigid and (has_numbered or has_answer_num)
    # Также считаем rigid если просто есть numbered disambig options
    if has_numbered and has_answer_num:
        is_rigid_format = True

    expect_rigid = scenario.get("expect_rigid", False)

    verdict = "OK"
    issue = None

    if not expect_rigid and is_rigid_format:
        verdict = "FAIL"
        issue = f"T{turn_num}: жёсткий disambiguation формат в ответе (контекст был ясен)"

    return {
        "turn": turn_num,
        "is_rigid_format": is_rigid_format,
        "has_organic_clarification": has_organic and not is_rigid_format,
        "has_tariff": has_tariff,
        "verdict": verdict,
        "issue": issue,
    }


# ---------------------------------------------------------------------------
# Запуск одного сценария
# ---------------------------------------------------------------------------
def run_scenario(scenario: dict, bot: SalesBot) -> dict:
    bot.reset()
    turns = []
    transitions = []
    checks = []
    prev_state = "greeting"
    start = time.time()

    for i, msg in enumerate(scenario["msgs"]):
        t0 = time.time()
        result = bot.process(msg)
        elapsed = round(time.time() - t0, 2)

        cur_state = result.get("state", "?")
        bot_text = result["response"]

        if cur_state != prev_state:
            transitions.append(f"T{i+1}: {prev_state} → {cur_state}")
            prev_state = cur_state

        chk = check_turn(bot_text, i + 1, scenario)
        checks.append(chk)

        turns.append({
            "turn": i + 1,
            "user": msg,
            "bot": bot_text,
            "state": cur_state,
            "action": result.get("action", "?"),
            "intent": result.get("intent", "?"),
            "template_key": result.get("template_key", "?"),
            "elapsed_s": elapsed,
            "is_final": result.get("is_final", False),
            "chk": chk,
        })

        if result.get("is_final"):
            break

    total_time = round(time.time() - start, 2)
    fail_checks = [c for c in checks if c["verdict"] == "FAIL"]

    # Для Group B: бонус за органичное уточнение
    organic_turns = [c for c in checks if c["has_organic_clarification"]]

    return {
        "id": scenario["id"],
        "group": scenario["group"],
        "name": scenario["name"],
        "desc": scenario["desc"],
        "expect_rigid": scenario.get("expect_rigid", False),
        "expect_clarification": scenario.get("expect_clarification", False),
        "transitions": transitions,
        "turns": turns,
        "checks": checks,
        "fail_checks": fail_checks,
        "organic_turns": len(organic_turns),
        "passed": len(fail_checks) == 0,
        "total_time_s": total_time,
        "num_turns": len(turns),
        "final_state": turns[-1]["state"] if turns else "?",
    }


# ---------------------------------------------------------------------------
# Форматирование
# ---------------------------------------------------------------------------
def format_result(d: dict) -> str:
    status = "✅ PASS" if d["passed"] else "❌ FAIL"
    lines = [
        f"\n{'='*80}",
        f"  {d['id']} [{d['group']}] {status} | {d['name']}",
        f"  {d['desc']}",
        f"  Ходов: {d['num_turns']} | Время: {d['total_time_s']}s | Финал: {d['final_state']}",
    ]
    if d.get("expect_clarification"):
        org = d.get("organic_turns", 0)
        lines.append(f"  Органичных уточнений: {org} {'✅' if org > 0 else '⚠️ нет'}")
    lines.extend([f"{'='*80}", ""])

    if d["transitions"]:
        lines.append("  ПЕРЕХОДЫ:")
        for t in d["transitions"]:
            lines.append(f"    🔄 {t}")
        lines.append("")

    if d["fail_checks"]:
        lines.append("  ПРОВАЛЫ:")
        for fc in d["fail_checks"]:
            lines.append(f"    ❌ {fc['issue']}")
            bot_text = next(
                (t["bot"] for t in d["turns"] if t["turn"] == fc["turn"]), ""
            )
            lines.append(f"       Ответ бота: «{bot_text[:250]}»")
        lines.append("")

    for t in d["turns"]:
        chk = t["chk"]
        if chk["is_rigid_format"]:
            icon = "🚨"  # жёсткий disambig
        elif chk["has_organic_clarification"]:
            icon = "🔍"  # органичное уточнение
        elif chk["has_tariff"]:
            icon = "💰"  # тариф назван
        else:
            icon = "  "

        fail_mark = " ← FAIL" if chk["verdict"] == "FAIL" else ""
        lines.append(DIVIDER)
        lines.append(
            f"  T{t['turn']} {icon} | state={t['state']} | intent={t['intent']} "
            f"| tmpl={t.get('template_key', '?')} | {t['elapsed_s']}s{fail_mark}"
        )
        lines.append(f"  К: {t['user']}")
        lines.append(f"  Б: {t['bot'][:400]}")
        lines.append("")

    return "\n".join(lines)


def build_summary(results: list, label: str = "") -> str:
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    group_a = [r for r in results if r["group"] == "A"]
    group_b = [r for r in results if r["group"] == "B"]
    group_c = [r for r in results if r["group"] == "C"]

    rigid_total = sum(
        1 for r in results
        for c in r["checks"]
        if c["is_rigid_format"]
    )
    organic_total = sum(r.get("organic_turns", 0) for r in results)

    lines = [
        f"\n{'='*80}",
        f"  {'[' + label + '] ' if label else ''}ИТОГ: {passed}/{total} PASS",
        f"  Group A (контекст ясен):     "
        f"{sum(1 for r in group_a if r['passed'])}/{len(group_a)}",
        f"  Group B (неясен, органично): "
        f"{sum(1 for r in group_b if r['passed'])}/{len(group_b)}",
        f"  Group C (крайние случаи):    "
        f"{sum(1 for r in group_c if r['passed'])}/{len(group_c)}",
        f"  Жёстких disambig: {rigid_total} | Органичных уточнений: {organic_total}",
        f"{'='*80}",
        "",
        "  | ID  | Гр | Статус  | Ходов | Финал                | Время  | Rigid | Organic |",
        "  |-----|----|---------| ------|----------------------|--------|-------|---------|",
    ]
    for r in results:
        status = "✅ PASS" if r["passed"] else "❌ FAIL"
        rigid_count = sum(1 for c in r["checks"] if c["is_rigid_format"])
        organic_count = r.get("organic_turns", 0)
        lines.append(
            f"  | {r['id']:<3} | {r['group']}  | {status} | "
            f"{r['num_turns']:<5} | {r['final_state']:<20} | {r['total_time_s']:.1f}s   "
            f"| {rigid_count:<5} | {organic_count:<7} |"
        )
    lines.append("")

    lines.append("  Disambiguation по ходам:")
    for r in results:
        rigid_turns = [
            f"T{c['turn']}" for c in r["checks"] if c["is_rigid_format"]
        ]
        organic_turns_list = [
            f"T{c['turn']}" for c in r["checks"] if c["has_organic_clarification"]
        ]
        lines.append(
            f"  {r['id']}: rigid={'🚨' + str(rigid_turns) if rigid_turns else '—'}, "
            f"organic={'🔍' + str(organic_turns_list) if organic_turns_list else '—'}"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    setup_autonomous_pipeline()
    # response_fact_disambiguation — NOT overridden, reads from settings.yaml

    llm = OllamaLLM()
    bot = SalesBot(llm, flow_name="autonomous")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = Path(__file__).parent.parent / "results"
    results_dir.mkdir(exist_ok=True)
    json_path = results_dir / f"disambig_e2e_{ts}.json"
    md_path = results_dir / f"disambig_e2e_{ts}.md"

    print(f"\n{'='*80}")
    print(f"  DISAMBIGUATION E2E — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  10 сценариев: A=контекст ясен, B=органичное уточнение, C=крайние")
    print(f"  LLM: {llm.model} @ {llm.base_url}")
    print(f"  response_fact_disambiguation: {flags.is_enabled('response_fact_disambiguation')}")
    print(f"{'='*80}")

    all_results = []
    for scenario in SCENARIOS:
        print(f"\n>>> [{scenario['id']}] {scenario['name']} ({len(scenario['msgs'])} ходов)...")
        result = run_scenario(scenario, bot)
        formatted = format_result(result)
        print(formatted)
        all_results.append(result)

    label = "disambiguation=ON" if flags.is_enabled("response_fact_disambiguation") else "disambiguation=OFF"
    summary = build_summary(all_results, label=label)
    print(summary)

    # --- JSON ---
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": ts,
                "label": label,
                "fact_disambiguation_enabled": flags.is_enabled("response_fact_disambiguation"),
                "scenarios": all_results,
            },
            f, ensure_ascii=False, indent=2, default=str,
        )

    # --- MD ---
    md_lines = [
        f"# Disambiguation E2E — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"## {label}",
        "",
        "## Сводка",
        summary,
        "",
        "## Диалоги",
    ]
    for r in all_results:
        md_lines.append(format_result(r))

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"\n  JSON: {json_path}")
    print(f"  MD:   {md_path}")

    total = len(all_results)
    passed = sum(1 for r in all_results if r["passed"])
    print(f"\n  ИТОГ: {passed}/{total} PASS\n")


if __name__ == "__main__":
    main()
