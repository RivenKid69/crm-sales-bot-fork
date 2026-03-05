"""
Повторная проверка Группы 1 (галлюцинации) после фикса.
"""
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.bot import SalesBot, setup_autonomous_pipeline
from src.llm import OllamaLLM

SCENARIOS = [
    {
        "id": "C04",
        "name": "Демо/тестовый период (KB: есть, 7 дней)",
        "msgs": [
            "Здравствуйте",
            "Мне нужна кассовая программа для аптеки",
            "Можно попробовать бесплатно перед покупкой?",
            "А демо-версия есть?",
            "Тогда давайте я просто куплю — как оформить?",
        ],
    },
    {
        "id": "C09",
        "name": "Несуществующие продукты — общепит, доставка, InDriver",
        "msgs": [
            "Здравствуйте",
            "У вас есть модуль для ресторанного бизнеса?",
            "А модуль доставки? Курьеры и всё такое",
            "Есть интеграция с Яндекс.Доставкой?",
            "Понял. Тогда расскажите что реально есть для розничной торговли",
        ],
    },
    {
        "id": "C06a",
        "name": "Контекст без истории — бот не должен выдумывать тип бизнеса",
        "msgs": [
            "Ещё один продавец ПО. Чем вы лучше других?",
            "У меня уже есть 1С, зачем мне ваше?",
        ],
    },
    {
        "id": "C05b",
        "name": "Казахский — правильное название тарифа",
        "msgs": [
            "Сәлем",
            "Менің дүкенім Алматыда, 2 касса",
            "Рахмет, бағасы қанша?",
        ],
    },
]

DIVIDER = "─" * 68

def run(scenario, bot):
    bot.reset()
    turns = []
    for i, msg in enumerate(scenario["msgs"]):
        r = bot.process(msg)
        turns.append({
            "t": i + 1,
            "user": msg,
            "bot": r["response"],
            "state": r.get("state", "?"),
            "action": r.get("action", "?"),
        })
        if r.get("is_final"):
            break
    return turns

def main():
    llm = OllamaLLM()
    setup_autonomous_pipeline()
    bot = SalesBot(llm, flow_name="autonomous")

    print(f"\n{'='*68}")
    print(f"  RECHECK ГРУППА 1 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*68}")

    for s in SCENARIOS:
        print(f"\n{DIVIDER}")
        print(f"  {s['id']} | {s['name']}")
        print(DIVIDER)
        turns = run(s, bot)
        for t in turns:
            print(f"\n[T{t['t']}] {t['state']} | {t['action']}")
            print(f"  👤 {t['user']}")
            print(f"  🤖 {t['bot']}")

if __name__ == "__main__":
    main()
