#!/usr/bin/env python3
"""
Прогон 3 упавших диалогов (D05, D08, D10) после фикса verifier grounding.
Проверяем что pain_context больше не отвергается factual_verifier'ом.

Запуск:
    python -m scripts.pain_verify_3fails 2>/dev/null
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.bot import SalesBot, setup_autonomous_pipeline
from src.llm import OllamaLLM
from src.knowledge.pain_retriever import (
    retrieve_pain_context,
    get_pain_retriever,
    _llm_has_pain_signal,
)

# 3 упавших сценария из pain_realistic_e2e_10
SCENARIOS: List[Dict[str, Any]] = [
    {
        "id": "D05",
        "name": "Кража кассира + недоверие",
        "pain_turn": 2,  # 0-indexed: ход 3
        "target_topic": "control_cashier_theft_103",
        "msgs": [
            "здрасте я ищу программу для магазина",
            "продукты, 1 точка, алматы, 5 сотрудников",
            "у нас тут проблема — подозреваю что кассирша ворует, удаляет позиции из чека а деньги себе, но доказать не могу потому что система ничего не логирует. вы это решаете?",
            "а она не сможет как нибудь обойти вашу систему?",
        ],
    },
    {
        "id": "D08",
        "name": "Бухгалтер ушел + 910 форма",
        "pain_turn": 2,  # 0-indexed: ход 3
        "target_topic": "consulting_dependency_on_one_accountant_3402",
        "msgs": [
            "добрый день",
            "у меня тоо, оптовая торговля, 15 человек в штате",
            "короче у нас бухгалтер уволился месяц назад, 910 форму скоро сдавать а мы вообще не понимаем как, учет весь в голове у нее был. есть у вас какой то сервис бухгалтерский?",
            "а сколько стоит ваш аутсорсинг бухгалтерии?",
        ],
    },
    {
        "id": "D10",
        "name": "Негатив без явной боли -> потом боль на 4 ходу",
        "pain_turn": 3,  # 0-indexed: ход 4
        "target_topic": "tis_limit_fear_1101",
        "msgs": [
            "здравствуйте",
            "мне нужна программа для автоматизации магазина стройматериалов",
            "3 точки, астана, каждый день по 200-300 чеков",
            "а вот еще вопрос, мы скоро наверно лимит по мрп превысим, оборот растет быстро, я боюсь что автоматом на ндс переведут. ваша система как то предупреждает об этом?",
            "ну если предупреждает то хорошо, а сколько стоит на 3 точки?",
        ],
    },
]

# Слова-маркеры "боли в ответе"
PAIN_RESPONSE_MARKERS = [
    "wipon", "система", "автоматическ", "контрол", "интеграц",
    "стабильн", "быстр", "оптимиз", "решен", "команд", "бухгалтер",
    "аутсорсинг", "учет", "лимит", "предупрежд", "мониторинг",
    "логир", "журнал", "отслежив", "удален", "лог", "отчет",
    "сопровожд", "непрерывн",
]

BAD_RESPONSES = [
    "недостаточно данных",
    "нет данных",
    "не располагаю",
    "не могу ответить",
    "уточню у коллег",
]


def run():
    print("=" * 80)
    print("  PAIN VERIFY — 3 ранее упавших диалога (D05, D08, D10)")
    print("  Проверка: pain_context теперь в grounding_facts verifier'а")
    print("=" * 80)
    print()

    setup_autonomous_pipeline()
    llm = OllamaLLM()

    pain_retriever = get_pain_retriever()
    print(f"Pain KB: {len(pain_retriever.kb.sections)} секций\n")

    results = []

    for scenario in SCENARIOS:
        sid = scenario["id"]
        name = scenario["name"]
        pain_idx = scenario["pain_turn"]
        target = scenario["target_topic"]
        msgs = scenario["msgs"]

        print(f"{'=' * 70}")
        print(f"  [{sid}] {name}")
        print(f"  Боль на ходу #{pain_idx + 1}, target: {target}")
        print(f"{'=' * 70}")

        bot = SalesBot(llm=llm, flow_name="autonomous")
        turns = []

        for i, msg in enumerate(msgs):
            t0 = time.time()

            # Isolated pain trace
            gate = _llm_has_pain_signal(llm=llm, user_message=msg, intent=None)
            pain_ctx = retrieve_pain_context(msg, intent=None, llm=llm)

            # Full pipeline
            result = bot.process(msg)
            elapsed = (time.time() - t0) * 1000

            bot_resp = result.get("response", "")
            is_pain = (i == pain_idx)
            marker = " <<<< PAIN" if is_pain else ""

            print(f"\n  ход {i+1}{marker}")
            print(f"  Клиент: {msg}")
            print(f"  gate={'YES' if gate else 'NO'}  pain_ctx={len(pain_ctx)}ch")
            if pain_ctx:
                lines = [l for l in pain_ctx.split("\n") if l.strip() and not l.startswith("===")]
                print(f"  preview: {' | '.join(lines)[:200]}")
            print(f"  Бот: {bot_resp[:400]}")

            turns.append({
                "turn": i + 1,
                "user": msg,
                "bot": bot_resp,
                "gate": gate,
                "pain_ctx_len": len(pain_ctx),
                "is_pain_turn": is_pain,
                "ms": round(elapsed),
            })

        # Verdict
        pt = turns[pain_idx]
        resp_lower = pt["bot"].lower()

        has_pain_ctx = pt["pain_ctx_len"] > 0
        has_bad = any(b in resp_lower for b in BAD_RESPONSES)
        has_marker = any(m in resp_lower for m in PAIN_RESPONSE_MARKERS)

        verdict = "PASS" if (has_pain_ctx and not has_bad and has_marker) else "FAIL"

        issues = []
        if not has_pain_ctx:
            issues.append("pain_ctx=ПУСТО")
        if has_bad:
            issues.append("BAD_RESPONSE в ответе!")
        if not has_marker:
            issues.append("нет маркеров боли в ответе")

        icon = "OK" if verdict == "PASS" else "!!"
        print(f"\n  [{icon}] {verdict}: ctx={pt['pain_ctx_len']}ch bad={has_bad} markers={has_marker}")
        if issues:
            print(f"  ISSUES: {'; '.join(issues)}")

        results.append({
            "id": sid,
            "name": name,
            "verdict": verdict,
            "issues": issues,
            "turns": turns,
        })

    # Summary
    passed = sum(1 for r in results if r["verdict"] == "PASS")
    print(f"\n{'=' * 70}")
    print(f"  ИТОГО: {passed}/{len(results)} PASS")
    print(f"{'=' * 70}")
    for r in results:
        icon = "OK" if r["verdict"] == "PASS" else "!!"
        print(f"  [{icon}] {r['id']} «{r['name']}» — {r['verdict']}")
        if r["issues"]:
            print(f"       {'; '.join(r['issues'])}")

    # Save
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path("results") / f"pain_verify_3fails_{ts}.json"
    out.parent.mkdir(exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"passed": passed, "total": len(results), "results": results},
                  f, ensure_ascii=False, indent=2)
    print(f"\nJSON: {out}")


if __name__ == "__main__":
    run()
