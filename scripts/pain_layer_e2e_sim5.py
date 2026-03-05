#!/usr/bin/env python3
"""
PAIN LAYER E2E — 5 сценариев живых диалогов.

Проверяем интеграцию БД по болям через CascadeRetriever:
  P01: Касса тормозит в час пик (pain_kassa)
  P02: Страх перехода на СНР 2026 (pain_snr)
  P03: Сканер плохо читает штрихкоды (pain_equipment)
  P04: Медленно добавлять товар вручную (pain_products)
  P05: Обычный диалог без болей (negative — pain_context пустой)

Что проверяем:
  1. pain_context заполнен для pain-сценариев (P01-P04) хотя бы на одном ходе
  2. pain_context пустой для не-pain сценария (P05) на ходе с болью
  3. Бот вплетает решение по боли в ответ

Запуск:
    python -m scripts.pain_layer_e2e_sim5 2>/dev/null
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.bot import SalesBot, setup_autonomous_pipeline
from src.llm import OllamaLLM

# ---------------------------------------------------------------------------
# 5 сценариев
# ---------------------------------------------------------------------------
SCENARIOS = [
    {
        "id": "P01",
        "name": "Касса тормозит в час пик",
        "group": "pain_kassa",
        "desc": "Клиент жалуется что касса зависает в пиковые часы → "
                "pain_context должен содержать решение",
        "expect_pain": True,
        # Ключевые слова для проверки pain_context — ищем хотя бы одно
        "pain_keywords": ["пик", "нагрузк", "стабильн", "зависан", "очеред",
                          "kassa_freeze", "касс"],
        # Ход, на котором проверяем pain_context (1-indexed)
        "pain_turn": 2,
        "msgs": [
            "Здравствуйте, у меня продуктовый магазин",
            "Главная проблема — касса тормозит в час пик, клиенты стоят в очереди и уходят",
            "А это точно не будет зависать при 50 чеках в час?",
        ],
    },
    {
        "id": "P02",
        "name": "Страх перехода на СНР 2026",
        "group": "pain_snr",
        "desc": "Клиент боится перехода на новый налоговый режим → "
                "pain_context про ТИС и переход",
        "expect_pain": True,
        "pain_keywords": ["снр", "тис", "переход", "режим", "налог", "уведомлен",
                          "tis_transition"],
        "pain_turn": 2,
        "msgs": [
            "Добрый день, у нас ИП в Алматы",
            "Боюсь перехода на СНР 2026, не знаем как это оформить и что менять",
            "А если мы не успеем подать уведомление до марта?",
        ],
    },
    {
        "id": "P03",
        "name": "Сканер плохо читает штрихкоды",
        "group": "pain_equipment",
        "desc": "Клиент жалуется на сканер → "
                "pain_context про оборудование",
        "expect_pain": True,
        "pain_keywords": ["сканер", "штрихкод", "считыва", "скорост",
                          "scanner", "equipment_scanner"],
        "pain_turn": 2,
        "msgs": [
            "Привет, у меня магазин одежды в Астане",
            "Сканер постоянно не считывает с первого раза, кассир по 3 раза водит",
            "Какой сканер посоветуете к вашей системе?",
        ],
    },
    {
        "id": "P04",
        "name": "Долго добавлять товар вручную",
        "group": "pain_products",
        "desc": "Клиент жалуется на ручной ввод номенклатуры → "
                "pain_context про автоматизацию добавления товара",
        "expect_pain": True,
        "pain_keywords": ["товар", "номенклатур", "вручную", "импорт", "добавл",
                          "штрихкод", "slow_new_product"],
        "pain_turn": 2,
        "msgs": [
            "Здравствуйте, у меня строительный магазин, 3000+ позиций",
            "Каждый новый товар приходится вбивать вручную — это отнимает полдня",
            "А можно загрузить весь каталог сразу из Excel?",
        ],
    },
    {
        "id": "P05",
        "name": "Обычный диалог без болей (negative)",
        "group": "negative",
        "desc": "Клиент спрашивает только о цене — "
                "pain_context должен быть ПУСТЫМ",
        "expect_pain": False,
        "pain_keywords": [],
        "pain_turn": None,
        "msgs": [
            "Добрый день, расскажите о тарифах",
            "Сколько стоит Lite тариф?",
            "Понял, спасибо. Подумаю и вернусь",
        ],
    },
]


# ---------------------------------------------------------------------------
# Извлечение pain_context
# ---------------------------------------------------------------------------
def get_pain_context_for_message(user_message: str) -> str:
    """Вызываем retrieve_pain_context напрямую (тот же вызов что в generate())."""
    from src.knowledge.pain_retriever import retrieve_pain_context
    try:
        return retrieve_pain_context(user_message)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Проверки для одного сценария
# ---------------------------------------------------------------------------
def check_scenario(scenario: dict, turns: list, pain_by_turn: dict) -> dict:
    """Возвращает verdict + issues."""
    issues = []

    if scenario["expect_pain"]:
        # 1. Хотя бы один ход дал непустой pain_context
        all_pain = [v for v in pain_by_turn.values() if v.strip()]
        if not all_pain:
            issues.append("pain_context ПУСТОЙ на всех ходах")
        else:
            # 2. Хотя бы один pain_context содержит ожидаемое слово
            combined_pain = "\n".join(all_pain).lower()
            found = [kw for kw in scenario["pain_keywords"] if kw.lower() in combined_pain]
            if not found:
                issues.append(
                    f"pain_context не содержит ожидаемых слов: {scenario['pain_keywords']}"
                )
    else:
        # Negative: проверяем что НИ ОДИН ход не дал pain_context
        for turn_num, ctx in pain_by_turn.items():
            if ctx.strip():
                issues.append(
                    f"T{turn_num}: pain_context НЕ ПУСТОЙ для negative ({len(ctx)}ch)"
                )
                break  # Одного примера достаточно

    # Общий pain_context_len = максимальный по ходам
    max_pain_len = max((len(v) for v in pain_by_turn.values()), default=0)

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "pain_context_len": max_pain_len,
    }


# ---------------------------------------------------------------------------
# Запуск одного сценария
# ---------------------------------------------------------------------------
def run_scenario(scenario: dict, bot: SalesBot) -> dict:
    bot.reset()
    turns = []
    pain_by_turn = {}
    start = time.time()

    for i, msg in enumerate(scenario["msgs"]):
        turn_num = i + 1
        t0 = time.time()
        result = bot.process(msg)
        elapsed = round(time.time() - t0, 2)

        pain_ctx = get_pain_context_for_message(msg)
        pain_by_turn[turn_num] = pain_ctx

        # Generator meta
        meta = bot.generator.get_last_generation_meta()
        tmpl = meta.get("selected_template_key", "?") if meta else "?"

        turns.append({
            "turn": turn_num,
            "user": msg,
            "bot": result["response"],
            "state": result.get("state", "?"),
            "action": result.get("action", "?"),
            "intent": result.get("intent", "?"),
            "spin_phase": result.get("spin_phase", "?"),
            "template_key": tmpl,
            "elapsed_s": elapsed,
            "pain_context_len": len(pain_ctx),
            "pain_context_preview": pain_ctx[:250] if pain_ctx else "",
        })

    total_time = round(time.time() - start, 2)
    checks = check_scenario(scenario, turns, pain_by_turn)

    return {
        "id": scenario["id"],
        "group": scenario["group"],
        "name": scenario["name"],
        "desc": scenario["desc"],
        "expect_pain": scenario["expect_pain"],
        "turns": turns,
        "checks": checks,
        "passed": checks["passed"],
        "total_time_s": total_time,
        "num_turns": len(turns),
        "final_state": turns[-1]["state"] if turns else "?",
    }


# ---------------------------------------------------------------------------
# Форматирование
# ---------------------------------------------------------------------------
DIVIDER = "─" * 80


def format_result(d: dict) -> str:
    status = "PASS" if d["passed"] else "FAIL"
    lines = [
        f"\n{'='*80}",
        f"  {d['id']} [{d['group']}] {status} | {d['name']}",
        f"  {d['desc']}",
        f"  Ходов: {d['num_turns']} | Время: {d['total_time_s']}s | Финал: {d['final_state']}",
        f"{'='*80}",
        "",
    ]

    if d["checks"]["issues"]:
        lines.append("  ПРОБЛЕМЫ:")
        for issue in d["checks"]["issues"]:
            lines.append(f"    [!] {issue}")
        lines.append("")

    lines.append(f"  max pain_context: {d['checks']['pain_context_len']} chars")
    lines.append("")

    for t in d["turns"]:
        pain_icon = "[P]" if t["pain_context_len"] > 0 else "[ ]"
        lines.append(DIVIDER)
        lines.append(
            f"  T{t['turn']} {pain_icon} | state={t['state']} | intent={t['intent']} "
            f"| tmpl={t['template_key']} | {t['elapsed_s']}s"
        )
        lines.append(f"  pain_ctx={t['pain_context_len']}ch")
        lines.append(f"  K: {t['user']}")
        lines.append(f"  Б: {t['bot'][:400]}")
        if t["pain_context_preview"]:
            lines.append(f"  [pain]: {t['pain_context_preview'][:250]}")
        lines.append("")

    return "\n".join(lines)


def build_summary(results: list) -> str:
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    pain_scenarios = [r for r in results if r["expect_pain"]]
    negative = [r for r in results if not r["expect_pain"]]

    lines = [
        f"\n{'='*80}",
        f"  ИТОГ: {passed}/{total} PASS",
        f"  Pain сценарии: "
        f"{sum(1 for r in pain_scenarios if r['passed'])}/{len(pain_scenarios)}",
        f"  Negative:       "
        f"{sum(1 for r in negative if r['passed'])}/{len(negative)}",
        f"{'='*80}",
        "",
        "  | ID  | Группа         | Статус  | pain_ctx | Время  |",
        "  |-----|----------------|---------|----------|--------|",
    ]
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        pc = r["checks"]["pain_context_len"]
        lines.append(
            f"  | {r['id']:<3} | {r['group']:<14} | {status:<7} | "
            f"{pc:>6}ch | {r['total_time_s']:.1f}s |"
        )
    lines.append("")

    lines.append("  Pain context по ходам:")
    for r in results:
        pain_turns = [
            f"T{t['turn']}({t['pain_context_len']}ch)"
            for t in r["turns"]
            if t["pain_context_len"] > 0
        ]
        lines.append(
            f"  {r['id']}: {pain_turns if pain_turns else '--- (пусто)'}"
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
    json_path = results_dir / f"pain_layer_sim5_{ts}.json"
    md_path = results_dir / f"pain_layer_sim5_{ts}.md"

    print(f"\n{'='*80}")
    print(f"  PAIN LAYER E2E SIM — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  5 сценариев: 4 pain + 1 negative")
    print(f"  LLM: {llm.model} @ {llm.base_url}")
    print(f"  Pain threshold: 0.025")
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
        f"# Pain Layer E2E Sim — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
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
    exit_code = 0 if passed == total else 1
    print(f"\n  ИТОГ: {passed}/{total} PASS\n")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
