#!/usr/bin/env python3
"""
PAIN REALISTIC E2E — 10 многоходовых диалогов.

Боль появляется на 3-5 ходу, утоплена в ценовых вопросах, ситуациях,
возражениях. Один бот на весь диалог, полный трейс pain_context на каждом ходу.

Запуск:
    python -m scripts.pain_realistic_e2e_10 2>/dev/null
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

# ---------------------------------------------------------------------------
# 10 реалистичных многоходовых сценариев
# ---------------------------------------------------------------------------
SCENARIOS: List[Dict[str, Any]] = [
    {
        "id": "D01",
        "name": "Касса тупит + цена в одном сообщении",
        "pain_turn": 3,  # 0-indexed turn where pain appears
        "target_topic": "kassa_freeze_peak_hours_601",
        "msgs": [
            "салам, мне друг посоветовал вас глянуть",
            "у нас 2 магазина продуктов в караганде",
            "ну мне тут сказали посмотреть, у нас касса иногда тупит при наплыве людей, а сколько стоит вообще ваша система?",
            "ну если тормозить не будет то может и возьмем",
        ],
    },
    {
        "id": "D02",
        "name": "Сканер + сколько точек + бюджет",
        "pain_turn": 2,
        "target_topic": "equipment_scanner_not_first_try_1703",
        "msgs": [
            "здравствуйте хочу узнать про вашу систему",
            "у нас аптека, 1 точка, примерно 3000 позиций",
            "главная проблема — сканер по 5 раз проводишь пока считает, клиенты психуют, и еще вопрос у вас рассрочка есть?",
            "ладно а маркировку поддерживаете? у нас же лекарства",
        ],
    },
    {
        "id": "D03",
        "name": "Боль в возражении на цену",
        "pain_turn": 3,
        "target_topic": "ops_speed_slow_new_product_add_002",
        "msgs": [
            "привет, мне нужна касса для магазина одежды",
            "а сколько стоит на 1 точку?",
            "дороговато если честно, я щас вручную в тетрадке все веду и товар добавляю по 2 часа каждую поставку, но все равно дорого",
            "ну а если на год то скидка есть какая нибудь?",
        ],
    },
    {
        "id": "D04",
        "name": "СНР страх спрятан в общем вопросе",
        "pain_turn": 2,
        "target_topic": "tis_transition_fear_new_regime_1001",
        "msgs": [
            "добрый день, я ип, розничная торговля",
            "слушайте а у вас есть что нибудь для учета налогов? мне бухгалтер сказала что с 2026 какие то изменения по снр и если не подготовимся то на общий режим переведут, я вообще в этом не разбираюсь",
            "а это прям автоматически все считает? я боюсь что штраф выпишут",
            "ну и сколько это стоит тогда",
        ],
    },
    {
        "id": "D05",
        "name": "Кража кассира + недоверие",
        "pain_turn": 3,
        "target_topic": "control_cashier_theft_103",
        "msgs": [
            "здрасте я ищу программу для магазина",
            "продукты, 1 точка, алматы, 5 сотрудников",
            "у нас тут проблема — подозреваю что кассирша ворует, удаляет позиции из чека а деньги себе, но доказать не могу потому что система ничего не логирует. вы это решаете?",
            "а она не сможет как нибудь обойти вашу систему?",
        ],
    },
    {
        "id": "D06",
        "name": "Ревизия + конкурент",
        "pain_turn": 2,
        "target_topic": "ops_speed_long_inventory_004",
        "msgs": [
            "мы сейчас на 1с сидим но думаем переехать",
            "основная причина — ревизия у нас 2 дня занимает каждый месяц, все вручную считаем, это капец. 1с вообще не помогает. у вас быстрее?",
            "а данные с 1с можно перенести к вам?",
            "ну и чо по цене на 3 точки",
        ],
    },
    {
        "id": "D07",
        "name": "Принтер сдох + уже злой",
        "pain_turn": 2,
        "target_topic": "equipment_printer_break_peak_1801",
        "msgs": [
            "вы продаете кассовое оборудование?",
            "короче у нас принтер чеков сдох вчера прям в самый час пик, мы полдня не торговали из за этого, продавцы на телефон чеки скидывали, бред. нужен нормальный принтер который не сломается через месяц, и желательно побыстрее доставить",
            "а гарантия на него какая?",
        ],
    },
    {
        "id": "D08",
        "name": "Бухгалтер ушел + 910 форма",
        "pain_turn": 3,
        "target_topic": "consulting_dependency_on_one_accountant_3402",
        "msgs": [
            "добрый день",
            "у меня тоо, оптовая торговля, 15 человек в штате",
            "короче у нас бухгалтер уволился месяц назад, 910 форму скоро сдавать а мы вообще не понимаем как, учет весь в голове у нее был. есть у вас какой то сервис бухгалтерский?",
            "а сколько стоит ваш аутсорсинг бухгалтерии?",
        ],
    },
    {
        "id": "D09",
        "name": "Электронный чек — боль внутри разговора о фичах",
        "pain_turn": 3,
        "target_topic": "kassa_no_e_receipt_604",
        "msgs": [
            "привет, расскажите что умеет ваша система",
            "нас интересует управление товарами и складом",
            "а еще вопрос — у нас клиенты постоянно просят чек на вотсап или на почту а мы не можем, только бумажный, это прям стыдно уже. это у вас есть?",
            "круто, а сколько стоит подключение?",
        ],
    },
    {
        "id": "D10",
        "name": "Негатив без явной боли → потом боль на 4 ходу",
        "pain_turn": 4,
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


def run_e2e():
    print("=" * 80)
    print("  PAIN REALISTIC E2E — 10 многоходовых диалогов")
    print("=" * 80)
    print()

    setup_autonomous_pipeline()
    llm = OllamaLLM()

    pain_retriever = get_pain_retriever()
    has_embeddings = bool(
        pain_retriever.use_embeddings and getattr(pain_retriever, "_embeddings_ready", False)
    )
    print(f"Pain KB: {len(pain_retriever.kb.sections)} секций, Embeddings: {'ON' if has_embeddings else 'OFF'}")
    print()

    all_results = []
    summary_lines = []

    for scenario in SCENARIOS:
        sid = scenario["id"]
        name = scenario["name"]
        pain_turn_idx = scenario["pain_turn"]
        target = scenario["target_topic"]
        msgs = scenario["msgs"]

        print(f"{'═' * 80}")
        print(f"  [{sid}] {name}")
        print(f"  Боль ожидается на ходу #{pain_turn_idx + 1}, target: {target}")
        print(f"{'═' * 80}")

        bot = SalesBot(llm=llm, flow_name="autonomous")
        dialog_trace = []

        for turn_idx, user_msg in enumerate(msgs):
            t0 = time.time()

            # --- Pain retrieval trace (isolated) ---
            search_results = pain_retriever.search(user_msg, top_k=2)
            gate = _llm_has_pain_signal(llm=llm, user_message=user_msg, intent=None)
            pain_ctx = retrieve_pain_context(user_msg, intent=None, llm=llm)

            # --- Full pipeline ---
            result = bot.process(user_msg)
            elapsed = (time.time() - t0) * 1000

            bot_response = result.get("response", "")
            intent = result.get("intent", "?")
            state = result.get("state", "?")
            action = result.get("action", "?")

            # --- Search details ---
            top_hit = None
            if search_results:
                top_hit = {
                    "topic": search_results[0].section.topic,
                    "category": search_results[0].section.category,
                    "score": round(search_results[0].score, 4),
                    "stage": search_results[0].stage.value,
                }

            is_pain_turn = (turn_idx == pain_turn_idx)
            gate_str = {True: "YES", False: "NO", None: "N/A"}.get(gate, "?")

            # --- Print ---
            marker = " <<<< PAIN TURN" if is_pain_turn else ""
            print(f"\n  ход {turn_idx + 1}{marker}")
            print(f"  Клиент: {user_msg}")
            print(f"  intent={intent}  state={state}  action={action}  [{elapsed:.0f}ms]")

            if top_hit:
                topic_match = "HIT" if top_hit["topic"] == target else "miss"
                print(f"  pain_search: {top_hit['category']}/{top_hit['topic']} "
                      f"score={top_hit['score']} stage={top_hit['stage']}  [{topic_match}]")
            else:
                print(f"  pain_search: ПУСТО")

            print(f"  pain_gate: {gate_str}  pain_ctx: {len(pain_ctx)}ch")

            # Show pain_context preview only if non-empty
            if pain_ctx:
                # Extract just the topic/facts, skip header
                lines = pain_ctx.split("\n")
                fact_lines = [l for l in lines if l.strip() and not l.startswith("===") and "вплети" not in l]
                preview = " | ".join(fact_lines)[:200]
                print(f"  pain_ctx_preview: {preview}")

            print(f"  Бот: {bot_response[:300]}")
            if len(bot_response) > 300:
                print(f"       ...+{len(bot_response) - 300}ch")

            turn_data = {
                "turn": turn_idx + 1,
                "user_msg": user_msg,
                "intent": intent,
                "state": state,
                "action": action,
                "pain_search_top": top_hit,
                "pain_gate": gate,
                "pain_context_len": len(pain_ctx),
                "bot_response": bot_response,
                "elapsed_ms": round(elapsed, 1),
                "is_pain_turn": is_pain_turn,
            }
            dialog_trace.append(turn_data)

        # --- Scenario verdict ---
        pain_turn_data = dialog_trace[pain_turn_idx]
        pain_found = pain_turn_data["pain_context_len"] > 0
        gate_ok = pain_turn_data["pain_gate"] is not False
        search_ok = (pain_turn_data["pain_search_top"] is not None)
        topic_hit = (
            pain_turn_data["pain_search_top"]["topic"] == target
            if pain_turn_data["pain_search_top"] else False
        )

        # Check if pain solution keywords appear in bot response on pain turn
        bot_resp_lower = pain_turn_data["bot_response"].lower()
        pain_in_response = any(word in bot_resp_lower for word in [
            "wipon", "система", "автоматическ", "контрол", "интеграц",
            "стабильн", "быстр", "оптимиз", "решен",
        ])

        issues = []
        if not search_ok:
            issues.append("search=ПУСТО")
        elif not topic_hit:
            top = pain_turn_data["pain_search_top"]["topic"]
            issues.append(f"topic={top} (ожидался {target})")
        if pain_turn_data["pain_gate"] is False:
            issues.append("gate=NO")
        if not pain_found:
            issues.append("pain_ctx=ПУСТО")
        if not pain_in_response:
            issues.append("боль НЕ в ответе бота")

        verdict = "PASS" if pain_found and gate_ok else "FAIL"
        icon = "OK" if verdict == "PASS" else "!!"

        print(f"\n  [{verdict}] pain_ctx={pain_turn_data['pain_context_len']}ch "
              f"gate={gate_ok} topic_hit={topic_hit} pain_in_resp={pain_in_response}")
        if issues:
            print(f"  ISSUES: {'; '.join(issues)}")

        summary_lines.append(
            f"  [{icon}] {sid} «{name}» "
            f"gate={'Y' if gate_ok else 'N'} "
            f"ctx={pain_turn_data['pain_context_len']:>4}ch "
            f"topic={'Y' if topic_hit else 'N'} "
            f"resp={'Y' if pain_in_response else 'N'} "
            f"{'| ' + '; '.join(issues) if issues else ''}"
        )

        all_results.append({
            "id": sid,
            "name": name,
            "target_topic": target,
            "pain_turn": pain_turn_idx + 1,
            "total_turns": len(msgs),
            "verdict": verdict,
            "issues": issues,
            "dialog": dialog_trace,
        })

    # --- Summary ---
    passed = sum(1 for r in all_results if r["verdict"] == "PASS")
    total = len(all_results)

    print(f"\n{'═' * 80}")
    print(f"  ИТОГО: {passed}/{total} PASS")
    print(f"{'═' * 80}")
    for line in summary_lines:
        print(line)

    # --- Save ---
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path("results") / f"pain_realistic_e2e_10_{ts}.json"
    out.parent.mkdir(exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": ts,
            "total": total,
            "passed": passed,
            "results": all_results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\nJSON: {out}")


if __name__ == "__main__":
    run_e2e()
