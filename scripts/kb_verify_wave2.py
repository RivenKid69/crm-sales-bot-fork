#!/usr/bin/env python3
"""
KB Fact Verification — ВОЛНА 2.
Проверяет новые области БД: фискализация, НКТ, интеграции, маркировка,
мобильное приложение, аналитика, сотрудники, склад.
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


# ===================== СЦЕНАРИИ ВОЛНА 2 =====================

SCENARIOS = {
    # --- ФИСКАЛИЗАЦИЯ / НКТ ---
    "w2_01_nkt_mandatory": [
        "Здравствуйте, у меня продуктовый магазин",
        "Что такое НКТ и обязателен ли он для розницы?",
    ],

    "w2_02_tax_forms": [
        "Добрый день, мне нужна онлайн-касса",
        "Формирует ли ваша программа налоговые формы? Какие именно?",
    ],

    "w2_03_ofd_cost": [
        "Привет, хочу подключить кассу",
        "Сколько стоит ОФД в месяц? Можно подключить ОФД отдельно без программы?",
    ],

    "w2_04_marking": [
        "Здравствуйте, у меня магазин с табачной продукцией",
        "Поддерживает ли Wipon маркировку товаров? Как это работает?",
    ],

    # --- БАНКИ И ТЕРМИНАЛЫ ---
    "w2_05_banks": [
        "Добрый день, мне нужен POS-терминал",
        "С какими банками вы работаете? Какие терминалы поддерживаете?",
    ],

    "w2_06_auto_sum": [
        "Здравствуйте, у меня розничный магазин",
        "При оплате картой кассиру нужно вводить сумму на терминале вручную?",
    ],

    "w2_07_multi_terminals": [
        "Привет, у меня магазин, хочу подключить терминалы от разных банков",
        "Можно подключить несколько POS-терминалов от разных банков к одной кассе?",
    ],

    "w2_08_kaspi_qr": [
        "Добрый день, многие клиенты платят через Kaspi",
        "Можно ли принимать оплату по Kaspi QR через вашу кассу?",
    ],

    # --- МАРКЕТПЛЕЙСЫ ---
    "w2_09_marketplaces": [
        "Здравствуйте, продаю через интернет",
        "Можно ли через Wipon продавать на Ozon и Wildberries? А на Kaspi Магазин?",
    ],

    # --- 1С И СМЕШАННАЯ ОПЛАТА ---
    "w2_10_1c_integration": [
        "Добрый день, у нас учёт ведётся в 1С",
        "Как устроена интеграция с 1С? Данные синхронизируются автоматически?",
    ],

    "w2_11_mixed_payment": [
        "Привет, у меня магазин одежды",
        "Клиент хочет оплатить часть наличными, часть картой. Можно так?",
    ],

    # --- МОБИЛЬНОЕ ПРИЛОЖЕНИЕ ---
    "w2_12_mobile_app": [
        "Здравствуйте, я часто в разъездах",
        "Есть ли мобильное приложение? На каких платформах работает?",
    ],

    "w2_13_offline_mobile": [
        "Добрый день, у меня точка в посёлке",
        "Если на телефоне пропадёт интернет — можно продолжать работать?",
    ],

    # --- СКЛАД И РЕВИЗИЯ ---
    "w2_14_inventory_audit": [
        "Здравствуйте, нужна инвентаризация",
        "Для ревизии надо закрывать магазин? Или можно продолжать продавать?",
    ],

    "w2_15_warehouses": [
        "Добрый день, у меня 4 склада",
        "Сколько складов можно вести в системе? Какой тариф нужен для 4 складов?",
    ],

    # --- АНАЛИТИКА ---
    "w2_16_analytics": [
        "Привет, хочу понимать какие товары приносят больше прибыли",
        "Есть ли ABC-анализ и отчёт по маржинальности?",
    ],

    # --- СОТРУДНИКИ ---
    "w2_17_employees_limit": [
        "Здравствуйте, у нас 15 сотрудников",
        "Сколько сотрудников можно добавить в тариф Standard? Есть ограничения?",
    ],

    "w2_18_cashier_control": [
        "Добрый день, у меня 3 кассира",
        "Можно ли отследить кто пробил ошибочный чек? Как контролировать кассиров?",
    ],

    # --- КОНФИДЕНЦИАЛЬНОСТЬ ---
    "w2_19_data_privacy": [
        "Привет, беспокоюсь за свои данные",
        "Налоговая видит все мои продажи и остатки на складе?",
    ],

    # --- ЭСФ/СНТ ---
    "w2_20_esf_snt": [
        "Здравствуйте, мне нужно работать с ЭСФ и СНТ",
        "Можно формировать и отправлять ЭСФ и СНТ через вашу программу?",
    ],
}

# Ожидаемые факты
EXPECTED_FACTS = {
    "w2_01_nkt_mandatory": {
        "must_contain_any": ["НКТ", "нкт", "каталог"],
        "description": "НКТ обязателен для розницы и опта, Wipon уже реализован",
    },
    "w2_02_tax_forms": {
        "must_contain_any": ["910", "913", "200"],
        "description": "Формы 910, 913, 200 — автоматически",
    },
    "w2_03_ofd_cost": {
        "must_contain_any": ["1 400", "1400", "1 120", "1120", "бесплатн", "включен", "входит"],
        "description": "ОФД стоимость (1400 или 1120₸/мес) или бесплатно при Wipon",
    },
    "w2_04_marking": {
        "must_contain_any": ["маркировк", "Data Matrix", "data matrix", "ISMET", "ismet", "Исмет"],
        "description": "Маркировка поддерживается: Data Matrix, ISMET",
    },
    "w2_05_banks": {
        "must_contain_any": ["Forte", "Halyk", "Kaspi", "Jysan", "Jýsan", "BCC",
                             "форте", "халык", "каспи", "жусан"],
        "description": "Банки: Forte, Halyk, Kaspi, Jysan, BCC",
    },
    "w2_06_auto_sum": {
        "must_contain_any": ["автоматическ", "не нужно", "не требуется", "без ручного",
                             "сама", "сам передаёт", "передаётся"],
        "description": "Сумма передаётся на терминал автоматически, ручной ввод не нужен",
    },
    "w2_07_multi_terminals": {
        "must_contain_any": ["несколько", "до 3", "до трёх", "разных банков",
                             "разные банки", "мультитерминал", "поддерживается"],
        "description": "До 3 POS-терминалов от разных банков",
    },
    "w2_08_kaspi_qr": {
        "must_contain_any": ["Kaspi QR", "kaspi qr", "Каспи QR", "QR", "qr",
                             "поддерживается", "поддерживаем", "можно", "да"],
        "description": "Kaspi QR поддерживается",
    },
    "w2_09_marketplaces": {
        "must_contain_any": ["Kaspi Магазин", "kaspi магазин", "Halyk Market", "halyk market",
                             "Каспи Магазин", "Халык Маркет", "каспи магазин"],
        "must_not_contain": [],  # Ozon/Wildberries — нет интеграции, бот должен сказать
        "description": "Kaspi Магазин и Halyk Market (не Ozon/Wildberries)",
    },
    "w2_10_1c_integration": {
        "must_contain_any": ["1С", "1C", "1с", "выгрузк", "экспорт", "обмен данными",
                             "интеграц"],
        "description": "1С интеграция: выгрузка данных (не прямая синхронизация)",
    },
    "w2_11_mixed_payment": {
        "must_contain_any": ["смешанн", "комбинированн", "два способа", "часть наличн",
                             "часть карт", "поддерживается", "можно", "да"],
        "description": "Смешанная оплата поддерживается",
    },
    "w2_12_mobile_app": {
        "must_contain_any": ["мобильн", "приложен", "iOS", "Android", "ios", "android",
                             "телефон", "смартфон"],
        "description": "Мобильное приложение: iOS и Android",
    },
    "w2_13_offline_mobile": {
        "must_contain_any": ["офлайн", "оффлайн", "без интернет", "синхрониз",
                             "сохран", "восстанов"],
        "description": "Офлайн-режим: работа без интернета, синхронизация позже",
    },
    "w2_14_inventory_audit": {
        "must_contain_any": ["без остановк", "продолжа", "не нужно закрыва", "не надо закрыва",
                             "ревизи", "инвентариз", "можно продавать"],
        "description": "Ревизия без остановки продаж",
    },
    "w2_15_warehouses": {
        "must_contain_any": ["3 склад", "5 склад", "до 3", "до 5", "Standard", "Pro",
                             "standard", "pro", "Стандарт", "Про"],
        "description": "Standard до 3 складов, Pro до 5 складов",
    },
    "w2_16_analytics": {
        "must_contain_any": ["ABC", "abc", "маржинальн", "прибыльн"],
        "description": "ABC-анализ и отчёт по маржинальности",
    },
    "w2_17_employees_limit": {
        "must_contain_any": ["без ограничен", "неограничен", "unlimited", "сколько угодно",
                             "Standard", "standard", "Стандарт"],
        "description": "Standard: сотрудники без ограничений",
    },
    "w2_18_cashier_control": {
        "must_contain_any": ["журнал", "отследи", "фиксиру", "привязан к кассиру",
                             "видно кто", "контрол", "история", "аудит",
                             "каждый чек", "под аккаунт"],
        "description": "Контроль кассиров: журнал, привязка чеков к кассиру",
    },
    "w2_19_data_privacy": {
        "must_contain_any": ["только чеки", "только фискальн", "не передаются",
                             "не видит", "остаются у вас", "остаются в систем",
                             "внутренни"],
        "description": "В налоговую — только фискальные чеки, остальное конфиденциально",
    },
    "w2_20_esf_snt": {
        "must_contain_any": ["ЭСФ", "СНТ", "эсф", "снт", "электронн", "счёт-фактур",
                             "счет-фактур"],
        "description": "ЭСФ и СНТ формируются и отправляются через Wipon",
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

    print(f"KB Verification Wave 2: {len(scenarios)} scenarios")
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
    outfile = f"results/kb_verify_wave2_{ts}.json"
    os.makedirs("results", exist_ok=True)
    with open(outfile, "w", encoding="utf-8") as f:
        json.dump({"summary": {"pass": pass_count, "fail": fail_count, "pct": pct},
                    "results": results}, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {outfile}")


if __name__ == "__main__":
    main()
