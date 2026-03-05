"""
Classifier Context E2E — 10 сценариев для проверки улучшений классификатора:
  1. Context-aware few-shot selection (priority+require_context)
  2. n_few_shot: 5→12
  3. dialog_history[-2:] в контексте классификации

Каждый сценарий стрессирует конкретный тип коротких/двусмысленных ответов.

Usage:
    python -m scripts.classifier_context_e2e
"""
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.bot import SalesBot, setup_autonomous_pipeline
from src.llm import OllamaLLM

SCENARIOS = [
    # ─────────────────────────────────────────────────────────────────────────
    # S01: Цепочка коротких ответов в discovery (dialog_history)
    # Бот задаёт вопросы, клиент отвечает односложно.
    # "Аптека", "3 точки", "Да, Алматы" должны классифицироваться правильно.
    # ─────────────────────────────────────────────────────────────────────────
    {
        "id": "S01",
        "name": "Короткие ответы в discovery (dialog_history)",
        "focus": "dialog_history + situation_provided",
        "msgs": [
            "Здравствуйте",
            "Аптека",
            "3 точки",
            "Да, все в Алматы",
            "Постоянные расхождения остатков между складом и кассой",
        ],
    },
    # ─────────────────────────────────────────────────────────────────────────
    # S02: "подумаю" в фазе presentation → objection_think, не request_brevity
    # ─────────────────────────────────────────────────────────────────────────
    {
        "id": "S02",
        "name": '"подумаю" в presentation → objection_think',
        "focus": "context-matched few-shot: spin_phase=presentation",
        "msgs": [
            "Здравствуйте, небольшой продуктовый магазин",
            "Основная проблема — инвентаризация занимает 2 дня каждый месяц",
            "Бюджет около 15 000 тенге в месяц",
            "Что именно подходит для продуктового?",
            "подумаю",
        ],
    },
    # ─────────────────────────────────────────────────────────────────────────
    # S03: "Да, всё устраивает" в closing → agreement, не demo_request
    # ─────────────────────────────────────────────────────────────────────────
    {
        "id": "S03",
        "name": '"Да, всё устраивает" в closing → agreement',
        "focus": "context-matched few-shot: state=autonomous_closing",
        "msgs": [
            "Здравствуйте, хочу Standard для магазина",
            "Проблема — нет учёта остатков, всё в Excel",
            "Бюджет есть, хотим подключить в этом месяце",
            "Отлично, давайте оформим",
            "87051234567",
            "Да, всё устраивает",
        ],
    },
    # ─────────────────────────────────────────────────────────────────────────
    # S04: "Давайте оформим" в negotiation → agreement + переход в closing
    # ─────────────────────────────────────────────────────────────────────────
    {
        "id": "S04",
        "name": '"Давайте оформим" в negotiation',
        "focus": "context-matched few-shot: state=autonomous_negotiation",
        "msgs": [
            "Добрый день",
            "Кофейня, 2 точки в Астане",
            "Нет единого учёта между точками",
            "Бюджет 20 000 тенге, хотим быстро",
            "Pro слишком дорого",
            "Standard подойдёт. Давайте оформим",
        ],
    },
    # ─────────────────────────────────────────────────────────────────────────
    # S05: "Да" как ответ на разные вопросы — dialog_history решает
    # ─────────────────────────────────────────────────────────────────────────
    {
        "id": "S05",
        "name": '"Да" на разные вопросы — dialog_history',
        "focus": "dialog_history disambiguation",
        "msgs": [
            "Здравствуйте, ювелирный магазин",
            "Да",          # ответ на вопрос бота про проблему/ситуацию
            "Да",          # ответ на вопрос про готовность к внедрению
            "Да, именно",  # подтверждение конкретной боли
            "Сколько это стоит?",
        ],
    },
    # ─────────────────────────────────────────────────────────────────────────
    # S06: Возражение по цене → смягчение → recovery
    # Проверяем нет ли stale price_question carryover после objection
    # ─────────────────────────────────────────────────────────────────────────
    {
        "id": "S06",
        "name": "Возражение по цене → смягчение (no stale carryover)",
        "focus": "objection_price → info_provided, нет carryover",
        "msgs": [
            "Привет, строительный магазин",
            "Проблема с учётом стройматериалов — артикулов тысячи",
            "500 000 в год — это дорого для нас",
            "Ну хорошо, а что входит в Standard?",
            "Понял, расскажите про интеграцию с весами",
        ],
    },
    # ─────────────────────────────────────────────────────────────────────────
    # S07: Быстрый покупатель — минимум хождений, прямо в closing
    # ─────────────────────────────────────────────────────────────────────────
    {
        "id": "S07",
        "name": "Быстрый покупатель — прямо к closing",
        "focus": "agreement + fast-track",
        "msgs": [
            "Добрый день",
            "Магазин спортивных товаров, 2 точки в Шымкенте. Нужен складской учёт и интеграция с Kaspi.",
            "Бюджет есть, хотим Standard. Сколько стоит на год?",
            "Хорошо, берём. Как оформить?",
            "87771234567",
        ],
    },
    # ─────────────────────────────────────────────────────────────────────────
    # S08: Смена темы — цена → фичи → возражение по цене снова
    # Проверяем что нет carryover intent после смены темы
    # ─────────────────────────────────────────────────────────────────────────
    {
        "id": "S08",
        "name": "Смена темы: цена → фичи → цена снова (no carryover)",
        "focus": "no stale intent carryover across topic switches",
        "msgs": [
            "Здравствуйте",
            "Кафе, 1 точка. Какие тарифы есть?",
            "А что умеет система вообще?",
            "Интеграция с Kaspi QR есть?",
            "Дорого. 500 в год много",
        ],
    },
    # ─────────────────────────────────────────────────────────────────────────
    # S09: Имя клиента в discovery → info_provided с contact_name extraction
    # ─────────────────────────────────────────────────────────────────────────
    {
        "id": "S09",
        "name": "Имя клиента в discovery → info_provided",
        "focus": "bare name classification (few-shot idx 13)",
        "msgs": [
            "Здравствуйте",
            "Меня зовут Асель",
            "У меня цветочный магазин в Алматы",
            "Проблема — нет учёта продаж по видам цветов",
            "Бюджет около 10 000 тенге, хотим быстро",
        ],
    },
    # ─────────────────────────────────────────────────────────────────────────
    # S10: Сложный клиент — 3 возражения подряд + финальное согласие
    # ─────────────────────────────────────────────────────────────────────────
    {
        "id": "S10",
        "name": "3 возражения подряд → финальное согласие",
        "focus": "multi-objection chain + agreement at end",
        "msgs": [
            "Здравствуйте",
            "Сеть аптек, 4 точки в Нур-Султане",
            "Контроль сроков годности и расхождения остатков — это наша главная боль",
            "Это дорого для нас",
            "Нам надо подумать",
            "А у нас нет времени сейчас заниматься внедрением",
            "Ладно, убедили. Давайте Standard. Как подключиться?",
        ],
    },
]

DIVIDER = "─" * 72


def run_dialog(scenario: dict, bot) -> dict:
    bot.reset()
    turns = []
    for i, msg in enumerate(scenario["msgs"]):
        result = bot.process(msg)
        turn = {
            "turn": i + 1,
            "user": msg,
            "bot": result["response"],
            "state": result.get("state", "?"),
            "action": result.get("action", "?"),
            "intent": result.get("intent", "?"),
            "spin_phase": result.get("spin_phase", "?"),
            "is_final": result.get("is_final", False),
        }
        turns.append(turn)
        if result.get("is_final"):
            break
    return {
        "id": scenario["id"],
        "name": scenario["name"],
        "focus": scenario["focus"],
        "turns": turns,
    }


def print_dialog(d: dict) -> str:
    lines = [
        f"\n{DIVIDER}",
        f"  {d['id']} | {d['name']}",
        f"  Фокус: {d['focus']}",
        DIVIDER,
    ]
    for t in d["turns"]:
        lines.append(
            f"\n[T{t['turn']}] state={t['state']} | intent={t['intent']} "
            f"| action={t['action']} | spin={t['spin_phase']}"
        )
        lines.append(f"  👤 {t['user']}")
        lines.append(f"  🤖 {t['bot'][:300]}")
        if t["is_final"]:
            lines.append("  ✅ ФИНАЛ")
    return "\n".join(lines)


def main():
    setup_autonomous_pipeline()

    llm = OllamaLLM()
    bot = SalesBot(llm, flow_name="autonomous")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(__file__).parent.parent / "results" / f"classifier_ctx_e2e_{ts}.json"
    out_path.parent.mkdir(exist_ok=True)

    print(f"\n{'='*72}")
    print(f"  CLASSIFIER CONTEXT E2E — 10 сценариев — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*72}")

    all_results = []
    for scenario in SCENARIOS:
        print(f"\n>>> {scenario['id']}: {scenario['name']}", flush=True)
        print(f"    Фокус: {scenario['focus']}", flush=True)
        d = run_dialog(scenario, bot)
        print(print_dialog(d))
        all_results.append(d)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"timestamp": ts, "scenarios": all_results}, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*72}")
    print(f"  Готово. JSON: {out_path}")
    print(f"{'='*72}")


if __name__ == "__main__":
    main()
