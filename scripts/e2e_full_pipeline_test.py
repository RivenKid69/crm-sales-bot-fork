"""
E2E test: 1 complex realistic dialog through full autonomous pipeline.

Tests the complete chain:
  Ollama (Qwen3.5-27B) + TEI Embed (Qwen3-Embedding-4B) + TEI Reranker (Qwen3-Reranker-4B)

Usage:
    python scripts/e2e_full_pipeline_test.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


SCENARIO = {
    "id": "E2E-FULL",
    "name": "Сеть продуктовых — полный SPIN цикл: greeting → discovery → pain → objection → pricing → скепсис → closing",
    "messages": [
        "Здравствуйте",
        "У нас сеть из 4 продуктовых магазинов в Караганде и один в Астане, думаем автоматизировать учёт",
        "Основная проблема — постоянные недостачи при инвентаризации, кассиры путаются с ценами, а я не могу из Астаны видеть что творится в Караганде",
        "Ну и ещё у нас сезонность — летом продаём больше воды и мороженого, зимой другие категории, и вручную перебивать цены на 5 точках — это ад",
        "А ваша система вообще надёжная? У нас до этого стояла одна программа, так она каждую неделю зависала",
        "Сколько будет стоить на все 5 точек?",
        "А что входит в этот тариф? Какие функции?",
        "Дороговато, у конкурентов я видел дешевле",
        "А поддержка у вас какая? Если в час пик всё зависнет — сколько ждать?",
        "Ну а рассрочка есть? Сразу всю сумму тяжело",
        "Ладно, давайте попробуем. Как подключиться?",
        "87071234567",
    ],
}


def run_scenario(scenario, bot):
    print(f"\n{'='*70}")
    print(f"  {scenario['id']}: {scenario['name']}")
    print(f"{'='*70}\n")

    bot.reset()
    turn_times = []

    for i, msg in enumerate(scenario["messages"]):
        t0 = time.time()
        result = bot.process(msg)
        elapsed = time.time() - t0
        turn_times.append(elapsed)

        response = result["response"]
        state = result.get("state", "?")
        action = result.get("action", "?")

        print(f"  [{i+1}] User: {msg}")
        print(f"      Bot:  {response[:600]}{'...' if len(response) > 600 else ''}")
        print(f"      [state={state}, action={action}, {elapsed:.1f}s]")
        print()

        if result.get("is_final"):
            print(f"  >>> TERMINAL STATE reached: {state}")
            break

    avg_time = sum(turn_times) / len(turn_times)
    print(f"\n{'='*70}")
    print(f"  Stats: {len(turn_times)} turns, avg {avg_time:.1f}s/turn, total {sum(turn_times):.1f}s")
    print(f"{'='*70}")
    return turn_times


def main():
    from src.bot import SalesBot, setup_autonomous_pipeline
    from src.llm import OllamaLLM

    print("Initializing pipeline...")
    t0 = time.time()
    llm = OllamaLLM()
    setup_autonomous_pipeline()
    bot = SalesBot(llm, flow_name="autonomous")
    print(f"Pipeline ready in {time.time() - t0:.1f}s\n")

    run_scenario(SCENARIO, bot)


if __name__ == "__main__":
    main()
