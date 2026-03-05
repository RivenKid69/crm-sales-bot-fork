#!/usr/bin/env python3
"""
KB Fact Verification — проверяет что бот корректно достаёт факты из обновлённой БД.
Каждый сценарий задаёт прямой вопрос → ответ должен содержать точные числа из БД.
"""

import json
import sys
import os
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.llm import OllamaClient
from src.bot import SalesBot, setup_autonomous_pipeline


def run_scenario(bot: SalesBot, name: str, messages: list) -> dict:
    """Run one scenario, return trace."""
    bot.reset()
    trace = []
    for idx, msg in enumerate(messages, 1):
        t0 = time.time()
        result = bot.process(msg)
        elapsed = time.time() - t0
        trace.append({
            "turn": idx,
            "user": msg,
            "bot": result.get("response", ""),
            "state": result.get("state", ""),
            "intent": result.get("intent", ""),
            "elapsed_s": round(elapsed, 2),
        })
        if result.get("is_final"):
            break
    return {"scenario": name, "trace": trace}


# ===================== СЦЕНАРИИ =====================
# Каждый проверяет конкретные факты из БД

SCENARIOS = {
    # --- ТАРИФЫ ---
    "kb01_tariff_prices": [
        "Здравствуйте, у меня магазин продуктов",
        "Какие у вас тарифы и цены?",
    ],

    "kb02_mini_details": [
        "Привет, у меня небольшой магазин",
        "Расскажите про тариф Mini — что входит и сколько стоит?",
    ],

    "kb03_lite_vs_standard": [
        "Добрый день, у меня 2 точки розничных",
        "Что лучше для двух точек — Lite или Standard? И сколько стоит каждый?",
    ],

    "kb04_pro_tariff": [
        "Здравствуйте, у меня сеть из 5 магазинов",
        "Расскажите про тариф Pro — цена и что входит?",
    ],

    # --- ТИС ---
    "kb05_tis_pricing": [
        "Добрый день, я ИП на упрощёнке",
        "Мне нужна ТИС для 3 точек. Сколько стоит?",
    ],

    "kb06_tis_10_points": [
        "Здравствуйте, у меня ИП на упрощёнке, 10 магазинов. Сколько обойдётся ТИС?",
    ],

    # --- ОБОРУДОВАНИЕ ---
    "kb07_pos_prices": [
        "Привет, мне нужен кассовый аппарат",
        "Какие POS-моноблоки есть и сколько стоят?",
    ],

    "kb08_bundle_prices": [
        "Добрый день, открываю магазин с нуля",
        "Мне нужен готовый комплект оборудования. Какие комплекты есть и цены?",
    ],

    "kb09_printers_scanners": [
        "Здравствуйте, у меня уже есть компьютер для кассы",
        "Нужен принтер для чеков и сканер штрих-кодов. Какие модели и цены?",
    ],

    "kb10_scales": [
        "Добрый день, у меня продуктовый магазин",
        "Мне нужны весы для товаров. Какие модели есть и сколько стоят?",
    ],

    # --- РАССРОЧКА ---
    "kb11_installment": [
        "Здравствуйте, можно в рассрочку оборудование купить?",
    ],

    # --- МОДУЛИ ---
    "kb12_pro_ukm": [
        "Привет, у меня магазин с алкоголем",
        "Нужен учёт акцизных товаров и маркировки. Что у вас для этого есть и сколько стоит?",
    ],

    # --- ОФД ---
    "kb13_ofd": [
        "Добрый день, у меня магазин, нужна касса с ОФД",
        "Сколько стоит ОФД у вас? И что входит?",
    ],

    # --- ПРОБНЫЙ ПЕРИОД ---
    "kb14_trial": [
        "Здравствуйте, интересует ваша система",
        "Хочу попробовать перед покупкой. Есть тестовый или пробный период?",
    ],

    # --- ФУНКЦИИ ---
    "kb15_offline_mode": [
        "Привет, у меня магазин в посёлке, интернет нестабильный",
        "Если интернет пропадёт — система будет работать?",
    ],

    "kb16_kaspi_integration": [
        "Добрый день, у меня магазин на Kaspi",
        "Есть ли интеграция с Kaspi? Как работает синхронизация?",
    ],

    "kb17_1c_integration": [
        "Здравствуйте, у нас учёт в 1С",
        "Можно ли синхронизировать Wipon с 1С?",
    ],

    # --- ПОДДЕРЖКА ---
    "kb18_support_info": [
        "Привет, думаю подключить Wipon",
        "А какая у вас техподдержка? Время работы, как связаться?",
    ],

    # --- ОБУЧЕНИЕ ---
    "kb19_training": [
        "Добрый день, у нас 10 сотрудников",
        "Нам нужно обучить персонал работе с системой. Есть обучение и сколько стоит?",
    ],

    # --- СЛОЖНЫЕ КОМБИНИРОВАННЫЕ ---
    "kb20_multi_question": [
        "Здравствуйте, у меня 3 точки продуктового",
        "Мне нужно: касса, сканер, принтер чеков, весы. Всё вместе сколько выйдет примерно?",
    ],
}

# Ожидаемые факты для каждого сценария (для проверки)
EXPECTED_FACTS = {
    "kb01_tariff_prices": {
        "must_contain_any": ["5 000", "5000", "150 000", "150000", "220 000", "220000", "500 000", "500000"],
        "description": "Должны быть цены тарифов (5000/150000/220000/500000)",
    },
    "kb02_mini_details": {
        "must_contain_any": ["5 000", "5000", "5 тыс"],
        "must_contain_all": [],
        "description": "Mini = 5000₸/мес, 1 точка, касса + фискализация",
    },
    "kb03_lite_vs_standard": {
        "must_contain_any": ["150 000", "150000", "220 000", "220000"],
        "description": "Lite=150000/год, Standard=220000/год. Standard для 3 точек",
    },
    "kb04_pro_tariff": {
        "must_contain_any": ["500 000", "500000"],
        "description": "Pro = 500000₸/год, 5 точек, 3 прайс-листа",
    },
    "kb05_tis_pricing": {
        "must_contain_any": ["220 000", "220000", "80 000", "80000"],
        "description": "ТИС: 220000 (1-я точка) + 80000 за доп. = 380000 за 3 точки",
    },
    "kb06_tis_10_points": {
        "must_contain_any": ["220 000", "220000", "80 000", "80000"],
        "description": "ТИС 10 точек: 220000 + 9×80000 = 940000₸/год",
    },
    "kb07_pos_prices": {
        "must_contain_any": ["140 000", "140000", "140 тыс", "160 000", "160000", "160 тыс",
                            "220 000", "220000", "220 тыс", "240 000", "240000", "240 тыс",
                            "300 000", "300000", "300 тыс", "330 000", "330000", "330 тыс",
                            "365 000", "365000", "365 тыс"],
        "description": "POS: i3=140k, i5=160k, DUO=220k, 5в1=240k, Premium=300k, Triple=330k, Quadro=365k",
    },
    "kb08_bundle_prices": {
        "must_contain_any": ["168 000", "168000", "219 000", "219000"],
        "description": "Комплекты: Standard=168000, Standard+=219000",
    },
    "kb09_printers_scanners": {
        "must_contain_any": ["15 000", "15000", "25 000", "25000", "10 000", "10000", "17 000", "17000"],
        "description": "Принтеры: GP-C58=15k, GP-C200I=25k. Сканеры: проводной=10k, беспроводной=17k",
    },
    "kb10_scales": {
        "must_contain_any": ["100 000", "100000", "200 000", "200000", "100 тыс", "200 тыс"],
        "description": "Весы: Wipon=100000, Rongta=200000",
    },
    "kb11_installment": {
        "must_contain_any": ["рассрочк", "Kaspi", "Каспи", "0-0-12", "12 месяц"],
        "description": "Рассрочка Kaspi 0-0-12",
    },
    "kb12_pro_ukm": {
        "must_contain_any": ["12 000", "12000", "УКМ", "маркировк", "алкогол"],
        "description": "PRO УКМ = 12000₸/год, учёт акцизных товаров",
    },
    "kb13_ofd": {
        "must_contain_any": ["1 400", "1400", "1 120", "1120", "бесплатн", "включен", "входит", "ОФД"],
        "description": "ОФД: стоимость (1400/1120₸) или бесплатно при Wipon",
    },
    "kb14_trial": {
        "must_contain_any": ["7 дней", "7 дн", "пробн", "тест", "бесплатн"],
        "description": "Пробный период 7 дней бесплатно",
    },
    "kb15_offline_mode": {
        "must_contain_any": ["офлайн", "оффлайн", "без интернет", "автоматическ", "синхронизац"],
        "description": "Офлайн-режим: работает без интернета, синхронизация при восстановлении",
    },
    "kb16_kaspi_integration": {
        "must_contain_any": ["Kaspi", "Каспи", "интеграц", "синхрониз"],
        "description": "Интеграция с Kaspi.kz: товары, заказы, остатки",
    },
    "kb17_1c_integration": {
        "must_contain_any": ["1С", "1C", "интеграц", "синхрониз", "экспорт", "импорт"],
        "description": "Интеграция с 1С: экспорт данных, импорт справочников",
    },
    "kb18_support_info": {
        "must_contain_any": ["поддержк", "ежедневн", "выходн", "чат", "10", "15"],
        "description": "Поддержка ежедневно включая выходные, ~10-15 мин ответ",
    },
    "kb19_training": {
        "must_contain_any": ["10 000", "10000", "обучен"],
        "description": "Обучение 10000₸/сессия",
    },
    "kb20_multi_question": {
        "must_contain_any": ["168 000", "168000", "219 000", "219000", "100 000", "100000",
                            "комплект", "Standard"],
        "description": "Должен предложить комплекты + весы отдельно",
    },
}


def check_facts(scenario_name: str, bot_responses: list) -> dict:
    """Check bot responses against expected facts."""
    all_text = " ".join(bot_responses).lower()
    expected = EXPECTED_FACTS.get(scenario_name, {})

    results = {
        "description": expected.get("description", ""),
        "pass": True,
        "issues": [],
    }

    # Check must_contain_any
    if "must_contain_any" in expected:
        found = [kw for kw in expected["must_contain_any"] if kw.lower() in all_text]
        if not found:
            results["pass"] = False
            results["issues"].append(f"MISS: none of {expected['must_contain_any']} found")
        else:
            results["found_keywords"] = found

    # Check must_contain_all
    if "must_contain_all" in expected:
        missing = [kw for kw in expected["must_contain_all"] if kw.lower() not in all_text]
        if missing:
            results["pass"] = False
            results["issues"].append(f"MISS_ALL: {missing} not found")

    # Check must_not_contain
    if "must_not_contain" in expected:
        found_bad = [kw for kw in expected["must_not_contain"] if kw.lower() in all_text]
        if found_bad:
            results["pass"] = False
            results["issues"].append(f"FORBIDDEN: {found_bad} found in response")

    return results


def main():
    # Select scenarios
    if len(sys.argv) > 1:
        selected = sys.argv[1].split(",")
        scenarios = {k: v for k, v in SCENARIOS.items() if k in selected}
    else:
        scenarios = SCENARIOS

    print(f"KB Verification: {len(scenarios)} scenarios")
    print("=" * 60)

    llm = OllamaClient()
    setup_autonomous_pipeline()
    bot = SalesBot(llm, flow_name="autonomous")

    results = []
    pass_count = 0
    fail_count = 0

    for name, messages in scenarios.items():
        print(f"\n{'='*60}")
        print(f"SCENARIO: {name}")
        print(f"{'='*60}")

        result = run_scenario(bot, name, messages)

        # Print dialog
        bot_responses = []
        for turn in result["trace"]:
            print(f"\n  [T{turn['turn']}] USER: {turn['user']}")
            print(f"  [T{turn['turn']}] BOT:  {turn['bot']}")
            print(f"  [T{turn['turn']}] state={turn['state']} intent={turn['intent']} ({turn['elapsed_s']}s)")
            bot_responses.append(turn["bot"])

        # Check facts
        check = check_facts(name, bot_responses)
        status = "PASS" if check["pass"] else "FAIL"

        if check["pass"]:
            pass_count += 1
        else:
            fail_count += 1

        print(f"\n  CHECK: {status} — {check['description']}")
        if check.get("found_keywords"):
            print(f"  FOUND: {check['found_keywords']}")
        for issue in check.get("issues", []):
            print(f"  ISSUE: {issue}")

        result["check"] = check
        results.append(result)

    # Summary
    total = pass_count + fail_count
    pct = (pass_count / total * 100) if total else 0
    print(f"\n{'='*60}")
    print(f"SUMMARY: {pass_count}/{total} PASS ({pct:.0f}%)")
    print(f"{'='*60}")

    if fail_count > 0:
        print("\nFAILED scenarios:")
        for r in results:
            if not r["check"]["pass"]:
                print(f"  - {r['scenario']}: {r['check']['issues']}")

    # Save
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = f"results/kb_verify_{ts}.json"
    os.makedirs("results", exist_ok=True)
    with open(outfile, "w", encoding="utf-8") as f:
        json.dump({"summary": {"pass": pass_count, "fail": fail_count, "pct": pct},
                    "results": results}, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {outfile}")


if __name__ == "__main__":
    main()
