#!/usr/bin/env python3
"""
POST5 E2E: 5 сложных сценариев для проверки state transitions после удаления
всех детерминированных overrides. LLM решает ВСЁ сам на основе контекста.

Фокус:
  T01 — Покупка из раннего стейта (presentation → closing)
  T02 — Цепочка возражений (остаётся в стейте, не скидывает в soft_close)
  T03 — Контакт посреди воронки (qualification → closing)
  T04 — Мягкое согласие vs покупка (agreement ≠ ready_to_buy)
  T05 — Экспресс-покупатель (greeting → closing → payment_ready за 5 ходов)
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.bot import SalesBot, setup_autonomous_pipeline
from src.llm import OllamaLLM

SCENARIOS = [
    # ═══════════════════════════════════════════════
    # T01: Покупка из раннего стейта
    # Клиент на презентации говорит "давайте оформим" →
    # LLM должен перескочить в closing, НЕ продолжать presentation
    # ═══════════════════════════════════════════════
    {
        "id": "T01",
        "name": "Покупка из раннего стейта — перескок в closing",
        "expected_transitions": [
            "greeting→autonomous_discovery",
            "autonomous_discovery→autonomous_qualification ИЛИ autonomous_presentation",
            "...→autonomous_closing (после 'давайте оформим')",
            "autonomous_closing→video_call_scheduled (после контакта)",
        ],
        "msgs": [
            "Здравствуйте",
            "У меня магазин одежды, 1 точка, 2 кассы",
            "Мне нужна кассовая программа с учётом остатков",
            "Какой тариф подойдёт для одного магазина?",
            "Давайте оформим Standard, мне всё понятно",
            "Как подключиться?",
            "Мой телефон 87071234567",
        ],
    },
    # ═══════════════════════════════════════════════
    # T02: Цепочка возражений — бот НЕ должен скидывать в soft_close
    # 3 возражения подряд (цена, конкурент, доверие) — бот остаётся
    # и работает с возражениями, НЕ уходит в soft_close
    # ═══════════════════════════════════════════════
    {
        "id": "T02",
        "name": "Цепочка возражений — не уходить в soft_close",
        "expected_transitions": [
            "Бот остаётся в текущем стейте при возражениях",
            "soft_close ТОЛЬКО при rejection ('не пишите больше')",
            "Возражения ≠ отказ",
        ],
        "msgs": [
            "Здравствуйте, у меня кафе, 3 точки",
            "Расскажите что есть для ресторанного бизнеса",
            "Дорого. У iiko за эти деньги больше функций",
            "Не уверен что ваша система справится с нашей нагрузкой — 500 чеков в день",
            "А если ваш сервер ляжет? У нас прошлый раз с другой системой потеряли данные за неделю",
            "И скидку мне никто не предложил — конкуренты дают 30% на первый год",
            "Ладно, допустим. А вот техподдержка — сколько ждать ответа?",
            "Хорошо, убедили. Давайте попробуем Standard на 3 точки",
            "87779998877",
        ],
    },
    # ═══════════════════════════════════════════════
    # T03: Контакт посреди воронки
    # Клиент в qualification вдруг говорит "позвоните мне 87..." →
    # LLM должен перейти в closing/video_call_scheduled
    # ═══════════════════════════════════════════════
    {
        "id": "T03",
        "name": "Контакт посреди воронки — скачок в closing",
        "expected_transitions": [
            "При contact_provided на раннем этапе → closing",
            "Затем closing→video_call_scheduled (контакт уже есть)",
        ],
        "msgs": [
            "Привет",
            "У меня автомагазин запчастей",
            "Мне некогда переписываться, позвоните мне лучше. Мой номер 87051112233",
            "Да, позвоните после 15:00",
        ],
    },
    # ═══════════════════════════════════════════════
    # T04: Мягкое согласие ≠ покупка
    # Клиент говорит "да, интересно", "согласен" — но это НЕ готовность купить.
    # LLM должен продолжить воронку, НЕ прыгать в closing.
    # Потом "хочу купить" → closing.
    # ═══════════════════════════════════════════════
    {
        "id": "T04",
        "name": "Мягкое согласие vs реальная покупка",
        "expected_transitions": [
            "'да, интересно' → НЕ closing (продолжает этап)",
            "'согласен, звучит неплохо' → НЕ closing",
            "'хочу оформить' → closing",
        ],
        "msgs": [
            "Здравствуйте, у меня цветочный магазин",
            "Расскажите что у вас есть",
            "Да, интересно. А какие тарифы?",
            "Согласен, звучит неплохо. А оборудование нужно ваше или своё подойдёт?",
            "Понятно. А Kaspi интегрируется?",
            "А скидки для новых клиентов есть?",
            "Хорошо, хочу оформить Lite. Что нужно?",
            "87473335566, запишите",
        ],
    },
    # ═══════════════════════════════════════════════
    # T05: Экспресс-покупатель — сразу к делу
    # Клиент не хочет разговоров, идёт к оплате максимально быстро.
    # greeting → closing → payment_ready за ~5 ходов.
    # ═══════════════════════════════════════════════
    {
        "id": "T05",
        "name": "Экспресс-покупатель — payment_ready за 5 ходов",
        "expected_transitions": [
            "Быстрый переход в closing (1-2 хода)",
            "closing→payment_ready (после kaspi_phone + ИИН)",
        ],
        "msgs": [
            "Здравствуйте, мне нужен Standard тариф на 1 точку. Сколько стоит и как оплатить?",
            "Понял, хочу купить. Выставьте счёт.",
            "Kaspi-телефон: 87019876543",
            "ИИН: 850610300123",
        ],
    },
]

DIVIDER = "─" * 80


def run_dialog(scenario: dict, bot: SalesBot) -> dict:
    """Запускает один диалог, собирает все метаданные + transitions."""
    bot.reset()
    turns = []
    transitions = []
    prev_state = "greeting"
    start = time.time()

    for i, msg in enumerate(scenario["msgs"]):
        t0 = time.time()
        result = bot.process(msg)
        elapsed = time.time() - t0

        cur_state = result.get("state", "?")
        if cur_state != prev_state:
            transitions.append(f"T{i+1}: {prev_state} → {cur_state}")
            prev_state = cur_state

        turn_data = {
            "turn": i + 1,
            "user": msg,
            "bot": result["response"],
            "state": cur_state,
            "action": result.get("action", "?"),
            "spin_phase": result.get("spin_phase", "?"),
            "intent": result.get("intent", "?"),
            "template_key": result.get("template_key", "?"),
            "is_final": result.get("is_final", False),
            "confidence": result.get("confidence", 0),
            "elapsed_s": round(elapsed, 2),
        }

        ed = result.get("extracted_data")
        if ed and isinstance(ed, dict):
            non_empty = {k: v for k, v in ed.items() if v}
            if non_empty:
                turn_data["extracted_data"] = non_empty

        turns.append(turn_data)
        if result.get("is_final"):
            break

    total_time = round(time.time() - start, 2)
    return {
        "id": scenario["id"],
        "name": scenario["name"],
        "expected_transitions": scenario["expected_transitions"],
        "actual_transitions": transitions,
        "turns": turns,
        "total_time_s": total_time,
        "num_turns": len(turns),
        "final_state": turns[-1]["state"] if turns else "?",
    }


def format_dialog(d: dict) -> str:
    """Форматирует диалог для отчёта."""
    lines = [
        f"\n{'='*80}",
        f"  {d['id']} | {d['name']}",
        f"  Ходов: {d['num_turns']} | Время: {d['total_time_s']}s | Финальный стейт: {d['final_state']}",
        f"{'='*80}",
        "",
        "  ОЖИДАЕМЫЕ ПЕРЕХОДЫ:",
    ]
    for et in d["expected_transitions"]:
        lines.append(f"    📋 {et}")

    lines.append("")
    lines.append("  ФАКТИЧЕСКИЕ ПЕРЕХОДЫ:")
    if d["actual_transitions"]:
        for at in d["actual_transitions"]:
            lines.append(f"    🔄 {at}")
    else:
        lines.append("    (нет переходов)")
    lines.append("")

    for t in d["turns"]:
        lines.append(DIVIDER)
        meta = (
            f"T{t['turn']} | state={t['state']} | intent={t['intent']} "
            f"| action={t['action']} | spin={t['spin_phase']} | {t['elapsed_s']}s"
        )
        lines.append(f"  [{meta}]")
        lines.append(f"  КЛИЕНТ: {t['user']}")
        lines.append(f"  БОТ:    {t['bot']}")
        if t.get("extracted_data"):
            lines.append(f"  📋 Извлечено: {t['extracted_data']}")
        if t["is_final"]:
            lines.append("  ✅ ФИНАЛ")
        lines.append("")

    return "\n".join(lines)


def main():
    setup_autonomous_pipeline()

    llm = OllamaLLM()
    bot = SalesBot(llm, flow_name="autonomous")

    all_results = []
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = Path(__file__).parent.parent / "results" / f"post5_transition_e2e_{ts}.json"
    md_path = Path(__file__).parent.parent / "results" / f"post5_transition_e2e_{ts}.md"
    json_path.parent.mkdir(exist_ok=True)

    print(f"\n{'='*80}")
    print(f"  POST5 TRANSITION E2E — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  5 сложных сценариев: переходы стейтов после удаления overrides")
    print(f"{'='*80}")

    for scenario in SCENARIOS:
        print(f"\n>>> [{scenario['id']}] {scenario['name']} ({len(scenario['msgs'])} ходов)...")
        dialog = run_dialog(scenario, bot)
        formatted = format_dialog(dialog)
        print(formatted)
        all_results.append(dialog)

    # --- Сводка ---
    print(f"\n{'='*80}")
    print("  СВОДКА ПЕРЕХОДОВ")
    print(f"{'='*80}")
    for d in all_results:
        status = "✅" if d["actual_transitions"] else "⚠️"
        print(f"\n  {status} {d['id']} | {d['name']}")
        print(f"     Финал: {d['final_state']}")
        for at in d["actual_transitions"]:
            print(f"     🔄 {at}")

    # --- JSON ---
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"timestamp": ts, "scenarios": all_results}, f, ensure_ascii=False, indent=2)

    # --- MD ---
    md_lines = [
        f"# POST5 Transition E2E — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## Сводка",
        "",
        "| ID | Сценарий | Ходов | Финальный стейт | Переходы |",
        "|----|----------|-------|-----------------|----------|",
    ]
    for d in all_results:
        trans = " → ".join(
            t.split(": ")[1] if ": " in t else t for t in d["actual_transitions"]
        ) or "нет"
        md_lines.append(
            f"| {d['id']} | {d['name']} | {d['num_turns']} | {d['final_state']} | {trans} |"
        )

    md_lines.append("")
    md_lines.append("## Диалоги")
    for d in all_results:
        md_lines.append(format_dialog(d))

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"\n  Результаты: {json_path}")
    print(f"  Отчёт:      {md_path}")


if __name__ == "__main__":
    main()
