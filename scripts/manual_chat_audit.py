"""
Ручной аудит 10 диалогов — взгляд от лица клиента.
Проверяет: логику диалога, ответы на прямые вопросы, точность по БД, SPIN-поток.
"""
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.bot import SalesBot, setup_autonomous_pipeline
from src.llm import OllamaLLM

# ──────────────────────────────────────────────
# 10 сценариев от лица разных клиентов
# ──────────────────────────────────────────────
SCENARIOS = [
    {
        "id": "C01",
        "name": "Прямой прайс-вопрос — небольшой продуктовый магазин",
        "msgs": [
            "Здравствуйте",
            "У меня небольшой продуктовый магазин, ищу кассовую программу",
            "Сколько стоит ваш продукт?",
            "А есть что-то дешевле?",
            "Ладно, расскажите подробнее про Mini",
        ],
    },
    {
        "id": "C02",
        "name": "Омоним 'стоит' — не должен дать ценовой ответ",
        "msgs": [
            "Здравствуйте, хочу узнать о системе",
            "Не стоит тратить время на лишние вопросы, скажите сразу — что умеет ваша программа?",
            "Сколько сотрудников может работать одновременно?",
        ],
    },
    {
        "id": "C03",
        "name": "Клиент сравнивает тарифы — Lite vs Standard",
        "msgs": [
            "Добрый день",
            "У меня магазин одежды, 3 кассира",
            "Чем Lite отличается от Standard?",
            "В Lite есть учёт остатков?",
            "А скидки для постоянных клиентов?",
        ],
    },
    {
        "id": "C04",
        "name": "Клиент просит демо/тестовый период",
        "msgs": [
            "Здравствуйте",
            "Мне нужна кассовая программа для аптеки",
            "Можно попробовать бесплатно перед покупкой?",
            "А демо-версия есть?",
            "Тогда давайте я просто куплю — как оформить?",
        ],
    },
    {
        "id": "C05",
        "name": "Казахскоязычный клиент — смешанный язык",
        "msgs": [
            "Сәлем, сізде кассалық бағдарлама бар ма?",
            "Менің дүкенім Алматыда, 2 касса",
            "Рахмет, бағасы қанша?",
            "Kaspi арқылы төлеуге болады ма?",
        ],
    },
    {
        "id": "C06",
        "name": "Скептичный клиент — возражения и давление",
        "msgs": [
            "Ещё один продавец ПО. Чем вы лучше других?",
            "У меня уже есть 1С, зачем мне ваше?",
            "Сколько стоит переход? Это же куча денег",
            "А если у вас сервер упадёт — я потеряю данные?",
            "Ладно, допустим. Расскажите про поддержку",
        ],
    },
    {
        "id": "C07",
        "name": "Сеть магазинов — Pro тариф, технические вопросы",
        "msgs": [
            "Добрый день, у нас 5 точек в разных городах Казахстана",
            "Нам нужен централизованный учёт по всем точкам",
            "Какая СУБД используется?",
            "Есть API для интеграции с нашей ERP?",
            "Сколько будет стоить для 5 точек на год?",
        ],
    },
    {
        "id": "C08",
        "name": "Клиент готов купить — быстрый путь к закрытию",
        "msgs": [
            "Здравствуйте, мне нужен Standard для магазина бытовой химии",
            "Да, всё понятно, как подключиться?",
            "Мой телефон 87051234567",
            "ИИН 850101300123",
        ],
    },
    {
        "id": "C09",
        "name": "Вопрос о чём-то несуществующем — тест на галлюцинации",
        "msgs": [
            "Здравствуйте",
            "У вас есть модуль для ресторанного бизнеса?",
            "А модуль доставки? Курьеры и всё такое",
            "Есть интеграция с Яндекс.Доставкой?",
            "Понял. Тогда расскажите что реально есть для розничной торговли",
        ],
    },
    {
        "id": "C10",
        "name": "Клиент прерывает SPIN — хочет сразу цену",
        "msgs": [
            "Привет",
            "Не надо вопросов — просто скажите цену на все тарифы",
            "Хорошо, а для одной кассы что берёте?",
            "Есть рассрочка?",
            "Договорились, хочу оформить. Как?",
        ],
    },
]

DIVIDER = "─" * 70


def run_dialog(scenario: dict, bot) -> dict:
    bot.reset()
    turns = []
    for i, msg in enumerate(scenario["msgs"]):
        result = bot.process(msg)
        turns.append({
            "turn": i + 1,
            "user": msg,
            "bot": result["response"],
            "state": result.get("state", "?"),
            "action": result.get("action", "?"),
            "spin_phase": result.get("spin_phase", "?"),
            "is_final": result.get("is_final", False),
        })
        if result.get("is_final"):
            break
    return {"id": scenario["id"], "name": scenario["name"], "turns": turns}


def print_dialog(d: dict) -> str:
    lines = [
        f"\n{DIVIDER}",
        f"  {d['id']} | {d['name']}",
        DIVIDER,
    ]
    for t in d["turns"]:
        lines.append(f"\n[T{t['turn']}] state={t['state']} | action={t['action']} | spin={t['spin_phase']}")
        lines.append(f"  👤 КЛИЕНТ: {t['user']}")
        lines.append(f"  🤖 БОТ:    {t['bot']}")
        if t["is_final"]:
            lines.append("  ✅ ФИНАЛ")
    return "\n".join(lines)


def main():
    llm = OllamaLLM()
    setup_autonomous_pipeline()
    bot = SalesBot(llm, flow_name="autonomous")

    all_results = []
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(__file__).parent.parent / "results" / f"chat_audit_{ts}.json"
    out_path.parent.mkdir(exist_ok=True)

    print(f"\n{'='*70}")
    print(f"  РУЧНОЙ АУДИТ 10 ДИАЛОГОВ — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*70}")

    for scenario in SCENARIOS:
        print(f"\n>>> Запускаю {scenario['id']}: {scenario['name']}")
        dialog = run_dialog(scenario, bot)
        print(print_dialog(dialog))
        all_results.append(dialog)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"timestamp": ts, "scenarios": all_results}, f, ensure_ascii=False, indent=2)
    print(f"\n\nРезультаты сохранены: {out_path}")


if __name__ == "__main__":
    main()
