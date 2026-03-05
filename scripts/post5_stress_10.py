#!/usr/bin/env python3
"""
POST5 STRESS: 10 сложных сценариев для проверки качества диалога и переходов.

S01 — Клиент меняет решение (хочу Pro → нет, дорого → ладно, Lite)
S02 — Два вопроса в одном сообщении + смена языка на казахский
S03 — Клиент-молчун (односложные ответы, бот должен вытягивать)
S04 — Возврат назад (клиент в negotiation просит вернуться к презентации)
S05 — Прямой отказ → мягкий возврат (rejection → потом "ну расскажите")
S06 — Клиент сравнивает с Poster и iiko одновременно
S07 — ИИН и Kaspi-телефон в одном сообщении → payment_ready
S08 — Клиент спрашивает то, чего нет в KB (фантастические функции)
S09 — Длинный диалог — 12 ходов через всю воронку
S10 — Клиент путает тарифы и оборудование, бот должен разобраться
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
    # S01: Клиент меняет решение трижды
    # Pro → дорого → Lite → нет, Standard → оформить
    # ═══════════════════════════════════════════════
    {
        "id": "S01",
        "name": "Меняет решение: Pro → дорого → Lite → Standard",
        "expected_transitions": [
            "Бот не зацикливается при смене выбора",
            "Финал: closing или video_call_scheduled",
        ],
        "msgs": [
            "Здравствуйте, у меня 3 магазина электроники",
            "Мне нужен Pro тариф, у нас большая сеть",
            "500 тысяч в год? Нет, это слишком дорого",
            "А что есть подешевле? Может Lite подойдёт?",
            "Подождите, а Standard на 3 точки потянет?",
            "Да, давайте Standard. Как оформить?",
            "87013456789",
        ],
    },
    # ═══════════════════════════════════════════════
    # S02: Два вопроса + смена языка
    # Русский → казахский → обратно → смешанный
    # ═══════════════════════════════════════════════
    {
        "id": "S02",
        "name": "Смена языка RU→KZ→RU + композитные вопросы",
        "expected_transitions": [
            "Бот адаптируется к языку",
            "Отвечает на оба вопроса в композите",
        ],
        "msgs": [
            "Привет, у меня продуктовый в Шымкенте",
            "Сколько стоит Lite и есть ли рассрочка?",
            "Түсінікті. Ал Standard неге қымбатырақ?",
            "Kaspi арқылы төлеуге бола ма?",
            "Ладно, вернёмся к русскому. А ОФД бесплатно подключается?",
            "Рахмет, Standard алайын. Телефоным 87751239988",
        ],
    },
    # ═══════════════════════════════════════════════
    # S03: Клиент-молчун
    # Односложные ответы — бот должен вытягивать информацию
    # ═══════════════════════════════════════════════
    {
        "id": "S03",
        "name": "Молчун — односложные ответы",
        "expected_transitions": [
            "Бот не повторяет один и тот же вопрос",
            "Прогрессирует по воронке несмотря на минимум информации",
        ],
        "msgs": [
            "Здравствуйте",
            "Магазин",
            "Одежда",
            "Один",
            "Да",
            "Не знаю",
            "Сколько стоит?",
            "Lite",
            "Оформляйте",
            "87021111111",
        ],
    },
    # ═══════════════════════════════════════════════
    # S04: Возврат назад по воронке
    # Клиент дошёл до negotiation и просит вернуться к функциям
    # ═══════════════════════════════════════════════
    {
        "id": "S04",
        "name": "Возврат назад — negotiation → презентация",
        "expected_transitions": [
            "go_back корректно возвращает на предыдущий этап",
            "Бот не теряет контекст после возврата",
        ],
        "msgs": [
            "Добрый день, у меня сеть аптек, 4 точки",
            "Нам нужен учёт маркированного товара и складской учёт",
            "Какой тариф подойдёт для 4 аптек?",
            "Standard за 220 тысяч — а чем Pro лучше?",
            "Подождите, вернёмся к функциям. Расскажите подробнее про ТИС",
            "А модуль для маркировки — это PRO УКМ? Сколько стоит?",
            "Понятно. Тогда Standard + PRO УКМ. Давайте оформим",
            "87474445566",
        ],
    },
    # ═══════════════════════════════════════════════
    # S05: Отказ → мягкий возврат
    # Клиент сначала отказывается, потом передумывает
    # ═══════════════════════════════════════════════
    {
        "id": "S05",
        "name": "Отказ → передумал → оформил",
        "expected_transitions": [
            "rejection → soft_close (или остаётся)",
            "Потом 'ну расскажите' → бот возвращается в диалог",
            "Финал: closing",
        ],
        "msgs": [
            "Здравствуйте, у меня небольшой магазин",
            "Нет, мне это не нужно, у меня и так всё работает",
            "Ну ладно, расскажите тогда что у вас есть, раз уж написали",
            "А сколько стоит самый простой вариант?",
            "Mini за 5000 в месяц? Это нормально. А что входит?",
            "Ладно, давайте попробуем Mini",
            "Мой номер 87019998877",
        ],
    },
    # ═══════════════════════════════════════════════
    # S06: Сравнение с двумя конкурентами
    # Poster и iiko — бот не должен выдумывать факты
    # ═══════════════════════════════════════════════
    {
        "id": "S06",
        "name": "Сравнение с Poster и iiko",
        "expected_transitions": [
            "Бот не выдумывает цены конкурентов",
            "Честно признаёт если данных нет",
        ],
        "msgs": [
            "Добрый день, у меня ресторан и бар, 2 точки",
            "Сейчас на Poster, но хочу сравнить. Чем вы лучше?",
            "А по сравнению с iiko? У них есть модуль бронирования столов",
            "Конкретно — ваш тариф Pro дешевле чем iiko Pro? Дайте цифры",
            "А интеграция с Glovo и Wolt есть? У Poster есть",
            "Ладно. А что уникального есть у вас, чего нет у других?",
            "Хорошо, убедили. Как подключиться?",
            "Позвоните мне: 87077776655",
        ],
    },
    # ═══════════════════════════════════════════════
    # S07: ИИН + Kaspi в одном сообщении → payment_ready
    # Клиент даёт все данные сразу — бот должен не потерять
    # ═══════════════════════════════════════════════
    {
        "id": "S07",
        "name": "ИИН + Kaspi в одном сообщении → payment_ready",
        "expected_transitions": [
            "closing → payment_ready за 1 ход (все данные сразу)",
        ],
        "msgs": [
            "Здравствуйте, мне нужен Standard на одну точку",
            "Хочу купить, выставьте счёт",
            "Мой Kaspi-телефон 87019876543, ИИН 900515300456",
        ],
    },
    # ═══════════════════════════════════════════════
    # S08: Фантастические запросы
    # Функции которых точно нет — бот должен честно отвечать
    # ═══════════════════════════════════════════════
    {
        "id": "S08",
        "name": "Несуществующие функции — тест на честность",
        "expected_transitions": [
            "Бот не выдумывает функции",
            "Честно говорит 'нет' или 'уточню'",
        ],
        "msgs": [
            "Здравствуйте, у меня строительный магазин",
            "Есть ли у вас модуль для управления проектами? Как Jira",
            "А видеонаблюдение через вашу систему можно подключить?",
            "Нужна интеграция с Яндекс Маркетом для продажи онлайн",
            "А AI-рекомендации для покупателей есть? Типа Amazon",
            "Ладно, а что реально есть для строительного магазина?",
            "Понятно. Сколько стоит Standard?",
            "Оформляйте, телефон 87023334455",
        ],
    },
    # ═══════════════════════════════════════════════
    # S09: Длинный диалог через всю воронку
    # discovery → qualification → presentation → objection → negotiation → closing
    # ═══════════════════════════════════════════════
    {
        "id": "S09",
        "name": "Полная воронка — 12 ходов",
        "expected_transitions": [
            "Проходит discovery → qualification → presentation → negotiation → closing",
            "Финал: video_call_scheduled или payment_ready",
        ],
        "msgs": [
            "Здравствуйте",
            "У меня сеть из 2 магазинов косметики в Астане",
            "Сейчас всё в Excel ведём, устали от ошибок",
            "Сколько точек и касс поддерживает ваша система?",
            "Бюджет — до 300 тысяч в год, потянем?",
            "Расскажите подробнее про Standard — что входит?",
            "А аналитика какая? ABC-анализ есть?",
            "Дороговато. А если на 2 года оплатить — скидка будет?",
            "А Kaspi Pay подключается? Нам важно принимать оплату через Kaspi",
            "Хорошо, берём Standard на 2 точки",
            "Как оформить? Нужен счёт",
            "Kaspi 87017654321, ИИН 851210400789",
        ],
    },
    # ═══════════════════════════════════════════════
    # S10: Путаница тарифов и оборудования
    # Клиент думает что "Standard" = оборудование, бот должен разобраться
    # ═══════════════════════════════════════════════
    {
        "id": "S10",
        "name": "Путаница тарифов и оборудования",
        "expected_transitions": [
            "Бот корректно различает тариф Standard и комплект Standard",
            "Не путает цены (тариф 220k vs комплект 168k)",
        ],
        "msgs": [
            "Здравствуйте, у меня магазин хозтоваров",
            "Сколько стоит Standard?",
            "А это с оборудованием или без?",
            "Мне нужно и программу и оборудование. Итого сколько выйдет?",
            "168 тысяч за оборудование + 220 тысяч за программу = 388 тысяч? Верно?",
            "А можно оборудование в рассрочку, а программу сразу оплатить?",
            "Ладно, давайте так и сделаем. Оформляйте",
            "87025556677",
        ],
    },
]

DIVIDER = "─" * 80


def run_dialog(scenario: dict, bot: SalesBot) -> dict:
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
    lines = [
        f"\n{'='*80}",
        f"  {d['id']} | {d['name']}",
        f"  Ходов: {d['num_turns']} | Время: {d['total_time_s']}s | Финал: {d['final_state']}",
        f"{'='*80}",
        "",
        "  ОЖИДАЕМЫЕ:",
    ]
    for et in d["expected_transitions"]:
        lines.append(f"    📋 {et}")
    lines.append("")
    lines.append("  ФАКТИЧЕСКИЕ ПЕРЕХОДЫ:")
    for at in d["actual_transitions"]:
        lines.append(f"    🔄 {at}")
    if not d["actual_transitions"]:
        lines.append("    (нет)")
    lines.append("")

    for t in d["turns"]:
        lines.append(DIVIDER)
        meta = (
            f"T{t['turn']} | state={t['state']} | intent={t['intent']} "
            f"| action={t['action']} | spin={t['spin_phase']} | {t['elapsed_s']}s"
        )
        lines.append(f"  [{meta}]")
        lines.append(f"  К: {t['user']}")
        lines.append(f"  Б: {t['bot']}")
        if t.get("extracted_data"):
            lines.append(f"  📋 {t['extracted_data']}")
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
    json_path = Path(__file__).parent.parent / "results" / f"post5_stress_10_{ts}.json"
    md_path = Path(__file__).parent.parent / "results" / f"post5_stress_10_{ts}.md"
    json_path.parent.mkdir(exist_ok=True)

    print(f"\n{'='*80}")
    print(f"  POST5 STRESS 10 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*80}")

    for scenario in SCENARIOS:
        print(f"\n>>> [{scenario['id']}] {scenario['name']} ({len(scenario['msgs'])} ходов)...")
        dialog = run_dialog(scenario, bot)
        formatted = format_dialog(dialog)
        print(formatted)
        all_results.append(dialog)

    # --- Сводка ---
    print(f"\n{'='*80}")
    print("  СВОДКА")
    print(f"{'='*80}\n")
    for d in all_results:
        final = d["final_state"]
        is_terminal = final in ("video_call_scheduled", "payment_ready", "soft_close")
        mark = "✅" if is_terminal else "⚠️"
        print(f"  {mark} {d['id']} | {d['name']}")
        print(f"     Финал: {final} | {d['num_turns']} ходов | {d['total_time_s']}s")
        for at in d["actual_transitions"]:
            print(f"     🔄 {at}")
        print()

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"timestamp": ts, "scenarios": all_results}, f, ensure_ascii=False, indent=2)

    md_lines = [
        f"# POST5 Stress 10 — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## Сводка",
        "",
        "| ID | Сценарий | Ходов | Финал | Время |",
        "|----|----------|-------|-------|-------|",
    ]
    for d in all_results:
        md_lines.append(f"| {d['id']} | {d['name']} | {d['num_turns']} | {d['final_state']} | {d['total_time_s']}s |")
    md_lines.append("")
    md_lines.append("## Диалоги")
    for d in all_results:
        md_lines.append(format_dialog(d))
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"  JSON: {json_path}")
    print(f"  MD:   {md_path}")


if __name__ == "__main__":
    main()
