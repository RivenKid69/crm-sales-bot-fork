#!/usr/bin/env python3
"""
PRICING DEFLECTION E2E — 15 targeted scenarios.

Фокус: "Точную стоимость уточню у коллег" — 8/40 ценовых дефлекций.
Три группы сценариев:

  GROUP A (S01–S09): Бот ДОЛЖЕН назвать тарифы, дефлекция = провал.
  GROUP B (S10–S11): Дефлекция корректна (технические вопросы без данных в KB).
  GROUP C (S12–S15): Сложные составные случаи — цена + фолбэк/валидатор/состояния.

Проверяемые патчи:
  Fix 1 — Rule #1 в SAFETY_RULES_V2: запрет "уточню у коллег" по стандартным тарифам.
  Fix 2 — _hallucination_fallback: grounded pricing fallback вместо дефлекции.
  Fix 3 — kb_categories для autonomous_discovery включает pricing.

Запуск:
    python -m scripts.pricing_deflection_e2e 2>/dev/null
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

# ---------------------------------------------------------------------------
# Тарифные паттерны: бот назвал хотя бы один тариф/цену
# ---------------------------------------------------------------------------
TARIFF_MENTION = re.compile(
    r'(?:'
    r'Mini|Lite|Standard|Pro|ТИС'
    r'|5\s*000\s*[₸Т]|5000\s*[₸Т]'
    r'|150\s*000\s*[₸Т]|150000\s*[₸Т]'
    r'|220\s*000\s*[₸Т]|220000\s*[₸Т]'
    r'|500\s*000\s*[₸Т]|500000\s*[₸Т]'
    r'|тари[фв]'       # "тариф", "тарифы"
    r')',
    re.IGNORECASE,
)

# Дефлекция — бот отказывается называть цену ссылаясь на коллег
DEFLECTION = re.compile(
    r'уточн[иую]\s+у\s+коллег',
    re.IGNORECASE,
)

# Технически допустимая дефлекция (SLA/СУБД/API) — для Group B
TECHNICAL_DEFLECTION = re.compile(
    r'уточн[иую].*?коллег|по\s+техническим\s+параметрам',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Сценарии
# ---------------------------------------------------------------------------
SCENARIOS = [

    # ════════════════════════════════════════════════
    # GROUP A: Бот ДОЛЖЕН назвать тарифы
    # ════════════════════════════════════════════════

    {
        "id": "S01",
        "group": "A",
        "name": "Голый вопрос о цене в discovery — первый же ход",
        "desc": (
            "Клиент открывает с вопроса о цене до любого контекста. "
            "Бот НЕ должен дефлектировать — тарифы известны."
        ),
        "expect_deflection": False,  # дефлекция = провал
        "msgs": [
            "Здравствуйте, сколько стоит?",
            "У меня один магазин одежды в Алматы",
            "Ок, подойдёт Lite. Как оформить?",
            "87711234567",
        ],
    },

    {
        "id": "S02",
        "group": "A",
        "name": "Казахский язык — цена на казахском в discovery",
        "desc": (
            "Клиент спрашивает цену на казахском. "
            "Бот должен ответить тарифами, не дефлектировать."
        ),
        "expect_deflection": False,
        "msgs": [
            "Сәлем, менде бір дүкен бар Астанада",
            "Барлығы неше теңге тұрады?",  # "Сколько всего стоит?"
            "Lite немесе Standard?",         # "Lite или Standard?"
            "Standard алайын. Байланыс: 87013456789",
        ],
    },

    {
        "id": "S03",
        "group": "A",
        "name": "Цена внедрения / установки — граничный случай",
        "desc": (
            "Клиент спрашивает 'сколько стоит внедрение?' — "
            "бот должен ответить тарифами (само ПО) и уточнить что входит. "
            "Не дефлектировать по стандартным ценам."
        ),
        "expect_deflection": False,
        "msgs": [
            "Добрый день, нас 2 точки продаж",
            "Сколько стоит внедрение вашей системы?",
            "А обучение персонала входит в стоимость?",
            "Standard за 220 — это за год? Не в месяц?",
            "Хорошо, оформляйте. Email: info@myshop.kz",
        ],
    },

    {
        "id": "S04",
        "group": "A",
        "name": "Клиент давит на цену с самого начала — 3 раза подряд",
        "desc": (
            "Клиент трижды спрашивает цену разными словами, не давая контекста. "
            "Бот должен ответить тарифами после первого вопроса, "
            "не уходить в дефлекцию при повторных попытках."
        ),
        "expect_deflection": False,
        "msgs": [
            "Привет, что по ценам?",
            "Ну хорошо, у меня магазин. Прайс есть?",
            "Просто скажи сколько стоит ваша программа",
            "Понял, Lite за 150 подходит. У меня одна касса",
            "87021111222",
        ],
    },

    {
        "id": "S05",
        "group": "A",
        "name": "Конкретное число касс → правильный тариф",
        "desc": (
            "Клиент сразу называет 3 кассы. "
            "Бот должен назвать Standard (до 5 точек) и цену 220 000 ₸/год. "
            "Не дефлектировать."
        ),
        "expect_deflection": False,
        "msgs": [
            "Здравствуйте, у меня 3 кассы в магазине стройматериалов",
            "Сколько будет стоить для нас?",
            "А скидка за 3 точки есть?",
            "Понял. Давайте Standard. Как подключиться?",
            "87775554433",
        ],
    },

    {
        "id": "S06",
        "group": "A",
        "name": "Ровно 5 точек — граница Pro/ТИС",
        "desc": (
            "5 точек — максимум для Pro. "
            "Бот должен назвать Pro 500 000 ₸/год и НЕ переходить сразу на ТИС. "
            "Не дефлектировать."
        ),
        "expect_deflection": False,
        "msgs": [
            "У нас сеть, 5 магазинов продуктовых",
            "Какой тариф подойдёт и сколько стоит?",
            "Pro за 500 тысяч — это в год, не в месяц?",
            "А если откроем 6-ю точку?",
            "Ясно. Пока 5. Оформляем Pro. Телефон: 87011122233",
        ],
    },

    {
        "id": "S07",
        "group": "A",
        "name": "Более 5 точек → ТИС, бот объясняет",
        "desc": (
            "10 точек — это ТИС (выше Pro). "
            "Бот должен объяснить что Pro до 5 точек, выше — ТИС, "
            "и не уходить в дефлекцию по Pro тарифам."
        ),
        "expect_deflection": False,
        "msgs": [
            "Добрый день, у нас 10 точек в Алматы и Астане",
            "Сколько стоит ваш топовый тариф?",
            "А что такое ТИС? Это другой продукт?",
            "Понял. Можете связать с коллегой по ТИС?",
            "Контакт: 87771234455",
        ],
    },

    {
        "id": "S08",
        "group": "A",
        "name": "Рассрочка + цена — клиент торгуется в discovery",
        "desc": (
            "Клиент хочет рассрочку и торгуется. "
            "Бот должен назвать тарифы И отвечать на рассрочку по KB. "
            "Не дефлектировать по основным ценам."
        ),
        "expect_deflection": False,
        "msgs": [
            "Здравствуйте, у меня обувной магазин в Шымкенте",
            "Сколько стоит и есть ли рассрочка?",
            "150 тысяч в год — дорого. Есть что-то в месяц?",
            "А Mini за 5000 в месяц — это с полным функционалом?",
            "Хочу Lite, но могу платить по 12 500 ежемесячно. Так можно?",
            "Ладно, оплачу сразу. Lite. Телефон: 87059876543",
        ],
    },

    {
        "id": "S09",
        "group": "A",
        "name": "Смена темы: клиент говорит о боли → вдруг спрашивает цену",
        "desc": (
            "Клиент обсуждал проблему с учётом, потом резко спрашивает цену. "
            "Контекст смены темы не должен вызывать дефлекцию. "
            "Бот называет тарифы."
        ),
        "expect_deflection": False,
        "msgs": [
            "У меня магазин электроники, постоянные расхождения в складском учёте",
            "Воруют или просто ошибки при приёмке — понять невозможно",
            "А, кстати, сколько вообще стоит ваша система?",
            "Standard за 220 в год — а в нём складской модуль есть?",
            "Хорошо. Давайте. Оформляйте",
            "87013456789",
        ],
    },

    # ════════════════════════════════════════════════
    # GROUP B: Дефлекция КОРРЕКТНА (технические вопросы)
    # ════════════════════════════════════════════════

    {
        "id": "S10",
        "group": "B",
        "name": "Технический вопрос — SLA (дефлекция допустима)",
        "desc": (
            "SLA/RPO/RTO нет в KB → 'уточню у коллег' корректен. "
            "При этом бот не должен дефлектировать по ценам если клиент их тоже спросит."
        ),
        "expect_deflection": True,  # дефлекция по SLA — ОК
        "msgs": [
            "Здравствуйте, у меня аптека",
            "Какой у вас SLA? Нам нужен uptime 99.99%",
            "А резервное копирование как часто?",
            "Ладно. А сколько стоит Standard?",  # здесь цену должен назвать
            "Понял. Спасибо, подумаю",
        ],
        # Специально: на T4 (цена) дефлекции не должно быть
        "price_turn": 4,  # на этом ходу проверяем что тарифы названы
    },

    {
        "id": "S11",
        "group": "B",
        "name": "Технический вопрос — СУБД (дефлекция допустима)",
        "desc": (
            "Какая СУБД нет в KB → 'уточню у коллег' корректен. "
            "Дефлекция технических деталей — не баг."
        ),
        "expect_deflection": True,
        "msgs": [
            "Добрый день, нам нужна интеграция с 1С",
            "Какая у вас СУБД? Нам важна совместимость",
            "А API для интеграции есть?",
            "Понял. Цены на Standard какие?",  # здесь цену должен назвать
            "Хорошо, подумаю. Спасибо",
        ],
        "price_turn": 4,
    },

    # ════════════════════════════════════════════════
    # GROUP C: Сложные составные случаи
    # ════════════════════════════════════════════════

    {
        "id": "S12",
        "group": "C",
        "name": "Negotiation state: торг по цене — бот не дефлектирует",
        "desc": (
            "В negotiation клиент пытается сбить цену. "
            "Бот называет тарифы из KB, не уходит в 'уточню у коллег'. "
            "Проверяем Fix 2 (_hallucination_fallback в negotiation)."
        ),
        "expect_deflection": False,
        "msgs": [
            "Добрый день, у меня 2 магазина",
            "Нам нужен склад + касса + аналитика",
            "Standard за 220 тысяч — а скидку дадите?",
            "Другие предлагают похожее за 150. Почему у вас дороже?",
            "Ладно, понял. Давайте Standard. Оформляем",
            "Email: buyer@store.kz",
        ],
    },

    {
        "id": "S13",
        "group": "C",
        "name": "Смешанный: цена + объём + казахский шум",
        "desc": (
            "Клиент задаёт сложный вопрос: несколько касс, казахский в середине, "
            "спрашивает и цену и функции одновременно. "
            "Бот называет тарифы и отвечает на функции."
        ),
        "expect_deflection": False,
        "msgs": [
            "Здравствуйте, бизнесіміз бар — 3 нүкте",  # казахский шум
            "Сколько стоит для нас и есть ли в системе складской учёт?",
            "Иә, Standard дұрыс па? Неше теңге?",   # Да, Standard правильно? Сколько?
            "220 тысяч в год — это с обновлениями?",
            "Жақсы, рахмет. Телефон: 87712345678",
        ],
    },

    {
        "id": "S14",
        "group": "C",
        "name": "Клиент-скептик: 'цены у вас нет, всё уточнять'",
        "desc": (
            "Клиент изначально настроен скептически — 'вы точно не скажете цену'. "
            "Бот опровергает это конкретными тарифами в первом же ответе."
        ),
        "expect_deflection": False,
        "msgs": [
            "Привет. Знаю что вы сейчас скажете 'уточним у менеджера'",
            "У меня продуктовый магазин, 1 касса. Сколько стоит?",
            "О, Mini за 5000 в месяц — хорошо. А Lite за 150 тысяч в год это выгоднее?",
            "Да, за год выгоднее. Берём Lite. Как оформить?",
            "87019998877",
        ],
    },

    {
        "id": "S15",
        "group": "C",
        "name": "Клиент сравнивает с конкурентом и спрашивает цену",
        "desc": (
            "Клиент упоминает конкурента и просит сравнить по цене. "
            "Бот называет свои тарифы (без сравнения с конкурентом), "
            "не дефлектирует."
        ),
        "expect_deflection": False,
        "msgs": [
            "У меня магазин, сейчас смотрю Poster и вас",
            "Poster стоит 6000 в месяц. Вы дешевле?",
            "Mini за 5000 — функционал такой же?",
            "А Lite за 150 тысяч в год — это 12 500 в месяц выходит?",
            "Понял. Lite выгоднее. Берём. 87015556677",
        ],
    },
]

DIVIDER = "─" * 80


# ---------------------------------------------------------------------------
# Проверка одного хода на предмет дефлекции / тарифа
# ---------------------------------------------------------------------------
def check_turn(bot_text: str, turn_num: int, scenario: dict) -> dict:
    has_tariff = bool(TARIFF_MENTION.search(bot_text))
    has_deflection = bool(DEFLECTION.search(bot_text))

    expect_deflection = scenario.get("expect_deflection", False)
    price_turn = scenario.get("price_turn")  # для Group B: ход где цену обязательно называть

    verdict = "OK"
    issue = None

    if expect_deflection:
        # Group B: ожидаем дефлекцию по техническим вопросам
        # НО если это price_turn — дефлекция = провал
        if price_turn and turn_num == price_turn:
            if has_deflection and not has_tariff:
                verdict = "FAIL"
                issue = f"T{turn_num}: дефлекция на turn с ценой — бот НЕ назвал тариф"
            elif has_tariff:
                verdict = "OK"
    else:
        # Group A/C: дефлекция по ценам = провал
        if has_deflection and not has_tariff:
            verdict = "FAIL"
            issue = f"T{turn_num}: дефлекция 'уточню у коллег' без называния тарифа"

    return {
        "turn": turn_num,
        "has_tariff": has_tariff,
        "has_deflection": has_deflection,
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

        # Проверка на дефлекцию / тариф
        chk = check_turn(bot_text, i + 1, scenario)
        checks.append(chk)

        turns.append({
            "turn": i + 1,
            "user": msg,
            "bot": bot_text,
            "state": cur_state,
            "action": result.get("action", "?"),
            "intent": result.get("intent", "?"),
            "spin_phase": result.get("spin_phase", "?"),
            "template_key": result.get("template_key", "?"),
            "elapsed_s": elapsed,
            "is_final": result.get("is_final", False),
            "chk": chk,
        })

        if result.get("is_final"):
            break

    total_time = round(time.time() - start, 2)
    fail_checks = [c for c in checks if c["verdict"] == "FAIL"]

    return {
        "id": scenario["id"],
        "group": scenario["group"],
        "name": scenario["name"],
        "desc": scenario["desc"],
        "expect_deflection": scenario.get("expect_deflection", False),
        "transitions": transitions,
        "turns": turns,
        "checks": checks,
        "fail_checks": fail_checks,
        "passed": len(fail_checks) == 0,
        "total_time_s": total_time,
        "num_turns": len(turns),
        "final_state": turns[-1]["state"] if turns else "?",
    }


# ---------------------------------------------------------------------------
# Форматирование отчёта
# ---------------------------------------------------------------------------
def format_result(d: dict) -> str:
    status = "✅ PASS" if d["passed"] else "❌ FAIL"
    lines = [
        f"\n{'='*80}",
        f"  {d['id']} [{d['group']}] {status} | {d['name']}",
        f"  {d['desc']}",
        f"  Ходов: {d['num_turns']} | Время: {d['total_time_s']}s | Финал: {d['final_state']}",
        f"{'='*80}",
        "",
    ]

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
            lines.append(f"       Ответ бота: «{bot_text[:200]}»")
        lines.append("")

    for t in d["turns"]:
        chk = t["chk"]
        # Иконка: тариф / дефлекция / ни то ни другое
        if chk["has_tariff"] and not chk["has_deflection"]:
            icon = "💰"
        elif chk["has_deflection"] and not chk["has_tariff"]:
            icon = "⚠️ " if d["expect_deflection"] else "🚨"
        elif chk["has_tariff"] and chk["has_deflection"]:
            icon = "💰⚠️"
        else:
            icon = "  "

        fail_mark = " ← FAIL" if chk["verdict"] == "FAIL" else ""
        lines.append(DIVIDER)
        lines.append(
            f"  T{t['turn']} {icon} | state={t['state']} | intent={t['intent']} "
            f"| {t['elapsed_s']}s{fail_mark}"
        )
        lines.append(f"  К: {t['user']}")
        lines.append(f"  Б: {t['bot'][:350]}")
        lines.append("")

    return "\n".join(lines)


def build_summary(results: list) -> str:
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    group_a = [r for r in results if r["group"] == "A"]
    group_b = [r for r in results if r["group"] == "B"]
    group_c = [r for r in results if r["group"] == "C"]

    lines = [
        f"\n{'='*80}",
        f"  ИТОГ: {passed}/{total} PASS",
        f"  Group A (не дефлектировать): "
        f"{sum(1 for r in group_a if r['passed'])}/{len(group_a)}",
        f"  Group B (дефлекция OK):      "
        f"{sum(1 for r in group_b if r['passed'])}/{len(group_b)}",
        f"  Group C (составные):         "
        f"{sum(1 for r in group_c if r['passed'])}/{len(group_c)}",
        f"{'='*80}",
        "",
        "  | ID  | Гр | Статус  | Ходов | Финал                | Время  |",
        "  |-----|----|---------| ------|----------------------|--------|",
    ]
    for r in results:
        status = "✅ PASS" if r["passed"] else "❌ FAIL"
        lines.append(
            f"  | {r['id']:<3} | {r['group']}  | {status} | "
            f"{r['num_turns']:<5} | {r['final_state']:<20} | {r['total_time_s']:.1f}s |"
        )
    lines.append("")

    # Дефлекции по ходам (для наглядного сравнения pre/post)
    lines.append("  Дефлекции по сценариям:")
    for r in results:
        deflect_turns = [
            f"T{t['turn']}" for t in r["turns"]
            if t["chk"]["has_deflection"] and not t["chk"]["has_tariff"]
        ]
        tariff_turns = [
            f"T{t['turn']}" for t in r["turns"]
            if t["chk"]["has_tariff"]
        ]
        lines.append(
            f"  {r['id']}: тарифы={tariff_turns or '—'}, "
            f"дефлекции={'🚨' + str(deflect_turns) if deflect_turns else '—'}"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    setup_autonomous_pipeline()

    llm = OllamaLLM()
    bot = SalesBot(llm, flow_name="autonomous")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = Path(__file__).parent.parent / "results"
    results_dir.mkdir(exist_ok=True)
    json_path = results_dir / f"pricing_deflection_{ts}.json"
    md_path = results_dir / f"pricing_deflection_{ts}.md"

    print(f"\n{'='*80}")
    print(f"  PRICING DEFLECTION E2E — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  15 сценариев: A=не дефлектировать, B=дефлекция OK, C=составные")
    print(f"  LLM: {llm.model} @ {llm.base_url}")
    print(f"{'='*80}")

    all_results = []
    for scenario in SCENARIOS:
        print(f"\n>>> [{scenario['id']}] {scenario['name']} ({len(scenario['msgs'])} ходов)...")
        result = run_scenario(scenario, bot)
        formatted = format_result(result)
        print(formatted)
        all_results.append(result)

    summary = build_summary(all_results)
    print(summary)

    # --- JSON ---
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {"timestamp": ts, "scenarios": all_results},
            f, ensure_ascii=False, indent=2, default=str,
        )

    # --- MD ---
    md_lines = [
        f"# Pricing Deflection E2E — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
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
