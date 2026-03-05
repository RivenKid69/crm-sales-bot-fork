#!/usr/bin/env python3
import json
import time
from datetime import datetime
from pathlib import Path

from src.bot import SalesBot, setup_autonomous_pipeline
from src.llm import OllamaLLM

DIALOGS = [
    {
        "id": "d1_list_then_all",
        "setup": "Здравствуйте, у меня продуктовый магазин в Алматы, 2 точки.",
        "turns": [
            "какие у вас есть тарифы",
            "назови все тарифы что у вас есть",
        ],
    },
    {
        "id": "d2_all_prices",
        "setup": "Привет, у нас магазин одежды в Астане.",
        "turns": [
            "перечисли все тарифы и цены",
        ],
    },
    {
        "id": "d3_compare_lite_standard",
        "setup": "Добрый день, у меня магазин электроники в Шымкенте.",
        "turns": [
            "сравни Lite и Standard по цене",
        ],
    },
    {
        "id": "d4_points_5",
        "setup": "Здравствуйте, у меня 5 торговых точек.",
        "turns": [
            "какой тариф нужен на 5 точек",
        ],
    },
    {
        "id": "d5_points_2",
        "setup": "Здравствуйте, у нас 2 магазина.",
        "turns": [
            "какой тариф для 2 точек",
        ],
    },
    {
        "id": "d6_points_6",
        "setup": "Здравствуйте, у меня 6 магазинов.",
        "turns": [
            "какой тариф для 6 точек",
        ],
    },
    {
        "id": "d7_mini_pro",
        "setup": "Добрый день, открываю магазин у дома.",
        "turns": [
            "сколько стоят Mini и Pro",
        ],
    },
    {
        "id": "d8_no_followup",
        "setup": "Привет, у нас один магазин.",
        "turns": [
            "назови все тарифы коротко без встречных вопросов",
        ],
    },
    {
        "id": "d9_tariffs_month_year",
        "setup": "Здравствуйте, у меня розничный бизнес.",
        "turns": [
            "какие тарифы у вас в месяц и в год",
        ],
    },
    {
        "id": "d10_tariff_for_3",
        "setup": "Здравствуйте, у меня 3 точки.",
        "turns": [
            "что посоветуете на 3 точки",
        ],
    },
]


def run(tag: str) -> Path:
    llm = OllamaLLM()
    setup_autonomous_pipeline()
    bot = SalesBot(llm, flow_name="autonomous", enable_tracing=True)

    results = {
        "timestamp": datetime.now().isoformat(),
        "tag": tag,
        "flow": "autonomous",
        "dialogs": [],
    }

    started = time.time()
    for dialog in DIALOGS:
        bot.reset()
        item = {
            "id": dialog["id"],
            "setup": dialog["setup"],
            "turns": [],
        }
        _ = bot.process(dialog["setup"])
        for user in dialog["turns"]:
            out = bot.process(user)
            item["turns"].append(
                {
                    "user": user,
                    "bot": out.get("response", ""),
                    "state": out.get("state", ""),
                    "action": out.get("action", ""),
                }
            )
        results["dialogs"].append(item)

    results["duration_s"] = round(time.time() - started, 2)

    out_path = Path("results") / f"autonomous_tariff_dialogs_{tag}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))
    return out_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    run(args.tag)
