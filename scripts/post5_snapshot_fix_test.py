#!/usr/bin/env python3
"""Quick retest: T01 and T04 — snapshot fix for terminal gate."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.bot import SalesBot, setup_autonomous_pipeline
from src.llm import OllamaLLM

SCENARIOS = [
    {
        "id": "T01",
        "name": "Покупка из раннего стейта",
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
    {
        "id": "T04",
        "name": "Мягкое согласие vs покупка",
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
]


def main():
    setup_autonomous_pipeline()

    llm = OllamaLLM()
    bot = SalesBot(llm, flow_name="autonomous")

    for sc in SCENARIOS:
        bot.reset()
        prev = "greeting"
        print(f"\n{'='*70}")
        print(f"  {sc['id']} | {sc['name']}")
        print(f"{'='*70}")

        for i, msg in enumerate(sc["msgs"]):
            t0 = time.time()
            r = bot.process(msg)
            dt = round(time.time() - t0, 1)
            st = r.get("state", "?")
            intent = r.get("intent", "?")
            arrow = f" → {st}" if st != prev else ""
            prev = st
            final = " ✅ ФИНАЛ" if r.get("is_final") else ""
            print(f"  T{i+1} [{st}] intent={intent} {dt}s{arrow}{final}")
            print(f"    К: {msg}")
            print(f"    Б: {r['response'][:120]}")
            if r.get("is_final"):
                break

        print(f"\n  Финальный стейт: {prev}")


if __name__ == "__main__":
    main()
