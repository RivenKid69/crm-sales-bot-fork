#!/usr/bin/env python3
"""
PAIN RETRIEVAL E2E — 20 разнообразных сообщений через полный автономный пайплайн.

Полный трейс каждого шага:
  1. Сообщение клиента (кривое, с ошибками)
  2. Классификация интента
  3. Pain gate (LLM бинарный классификатор: YES/NO)
  4. Pain retrieval (CascadeRetriever: exact/lemma/semantic)
  5. pain_context — что попало в промпт
  6. retrieved_facts — основная БД
  7. Финальный ответ бота
  8. Оценка: встроена ли боль в ответ

Запуск:
    python -m scripts.pain_retrieval_e2e_20 2>/dev/null
"""

import sys
import json
import time
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.bot import SalesBot, setup_autonomous_pipeline
from src.llm import OllamaLLM
from src.knowledge.pain_retriever import (
    retrieve_pain_context,
    get_pain_retriever,
    _llm_has_pain_signal,
    _PAIN_TOP_K,
)

# ---------------------------------------------------------------------------
# 20 кривых сообщений от реальных клиентов
# ---------------------------------------------------------------------------
MESSAGES: List[Dict[str, Any]] = [
    # --- pain_kassa ---
    {
        "id": "M01",
        "msg": "слушай у нас каса виснет когда народ повалит после обеда, прям все стоят ждут",
        "target_topic": "kassa_freeze_peak_hours_601",
        "target_category": "pain_kassa",
        "pain_keywords": ["пик", "нагрузк", "стабильн", "зависан", "чек"],
    },
    {
        "id": "M02",
        "msg": "мы кассу хотели зарегить но блин такой гемор с офд этим, уже 3 день мучаемся",
        "target_topic": "kassa_registration_long_602",
        "target_category": "pain_kassa",
        "pain_keywords": ["ОФД", "регистрац", "подключен", "онлайн"],
    },
    {
        "id": "M03",
        "msg": "девочки новые путаются на касе, кнопок куча, то один товар пробьют то другой и ошибки постоянно",
        "target_topic": "kassa_complex_interface_603",
        "target_category": "pain_kassa",
        "pain_keywords": ["интерфейс", "ошибк", "обучен", "интуитивн"],
    },
    {
        "id": "M04",
        "msg": "клиенты спрашивают можно чек на ватсап скинуть а у нас нету такого вообще",
        "target_topic": "kassa_no_e_receipt_604",
        "target_category": "pain_kassa",
        "pain_keywords": ["WhatsApp", "электронн", "чек", "email"],
    },
    # --- pain_equipment ---
    {
        "id": "M05",
        "msg": "принтер бл печатает так медлено что очередь из за него стоит а не из за кассира",
        "target_topic": "equipment_slow_printer_1701",
        "target_category": "pain_equipment",
        "pain_keywords": ["принтер", "печат", "скорост", "задерж"],
    },
    {
        "id": "M06",
        "msg": "сканер наш дурацкий с 3его раза только считывает штрихкод, кассир по 5 раз проводит",
        "target_topic": "equipment_scanner_not_first_try_1703",
        "target_category": "pain_equipment",
        "pain_keywords": ["сканер", "считыван", "штрихкод", "1D", "2D"],
    },
    {
        "id": "M07",
        "msg": "комп на касе вобще тупой, зависает намертво при наплыве покупателей, хотим нормальный",
        "target_topic": "equipment_weak_pos_pc_1706",
        "target_category": "pain_equipment",
        "pain_keywords": ["POS", "моноблок", "SSD", "памят", "нагрузк"],
    },
    {
        "id": "M08",
        "msg": "у нас в час пик принтер сдох прям на глазах, чеки встали и все продажи тоже",
        "target_topic": "equipment_printer_break_peak_1801",
        "target_category": "pain_equipment",
        "pain_keywords": ["принтер", "надежн", "интенсивн", "автообрезк"],
    },
    # --- pain_snr ---
    {
        "id": "M09",
        "msg": "короч мне сказали что с 2026 снр меняется и если не подашь что то то переведут на общий, вот боюсь",
        "target_topic": "tis_transition_fear_new_regime_1001",
        "target_category": "pain_snr",
        "pain_keywords": ["СНР", "режим", "переход", "2026"],
    },
    {
        "id": "M10",
        "msg": "блин я не подал уведомление до 1го марта и теперь вроде на общий режим кинут, чо делать",
        "target_topic": "tis_transition_auto_general_regime_1002",
        "target_category": "pain_snr",
        "pain_keywords": ["уведомлен", "общий режим", "срок", "перевод"],
    },
    {
        "id": "M11",
        "msg": "у нас оборот растет хорошо но я боюсь что лимит в 600тыс мрп скоро превысим и чо будет",
        "target_topic": "tis_limit_fear_1101",
        "target_category": "pain_snr",
        "pain_keywords": ["лимит", "600", "МРП", "оборот", "контрол"],
    },
    {
        "id": "M12",
        "msg": "форму 910 новую не могу заполнить, поменяли все нахрен, бухгалтер тоже не понимает",
        "target_topic": "tis_reporting_new_forms_complexity_1201",
        "target_category": "pain_snr",
        "pain_keywords": ["910", "форм", "отчетност", "автоматическ"],
    },
    # --- pain_products ---
    {
        "id": "M13",
        "msg": "товар новый добавлять в систему — это ваще жесть, вручную каждую позицию вбиваем час",
        "target_topic": "ops_speed_slow_new_product_add_002",
        "target_category": "pain_products",
        "pain_keywords": ["импорт", "автозаполн", "номенклатур", "штрихкод"],
    },
    {
        "id": "M14",
        "msg": "ревизия у нас целый день занимает, пересчитываем все руками, это жестко вобще",
        "target_topic": "ops_speed_long_inventory_004",
        "target_category": "pain_products",
        "pain_keywords": ["ревизи", "сканер", "мобильн", "остатк"],
    },
    {
        "id": "M15",
        "msg": "тут короч пропал товар, кто менял остатки непонятно, журнал никакого нету",
        "target_topic": "control_no_history_101",
        "target_category": "pain_products",
        "pain_keywords": ["истори", "операц", "сотрудник", "фиксац"],
    },
    {
        "id": "M16",
        "msg": "кассирша наша удаляет позиции из чека тихонько и деньги в карман, мы только потом замечаем",
        "target_topic": "control_cashier_theft_103",
        "target_category": "pain_products",
        "pain_keywords": ["кассир", "фиксац", "действ", "контрол", "удален"],
    },
    # --- pain_consulting ---
    {
        "id": "M17",
        "msg": "налоговая прислала запрос а я вобще не понимаю что отвечать, кгд какой то",
        "target_topic": "consulting_tax_communication_difficulty_3404",
        "target_category": "pain_consulting",
        "pain_keywords": ["КГД", "запрос", "ответ", "представительств"],
    },
    {
        "id": "M18",
        "msg": "хочу ип открыть но нифига не понимаю какие документы надо и куда идти",
        "target_topic": "consulting_ip_registration_difficulty_3201",
        "target_category": "pain_consulting",
        "pain_keywords": ["ИП", "регистрац", "документ", "сопровожден"],
    },
    {
        "id": "M19",
        "msg": "бухгалтер уволилась и учет встал, все в одной голове было и теперь мы в жопе",
        "target_topic": "consulting_dependency_on_one_accountant_3402",
        "target_category": "pain_consulting",
        "pain_keywords": ["бухгалтер", "команд", "непрерывност", "учет"],
    },
    {
        "id": "M20",
        "msg": "я вроде переплачиваю налогов дохрена, может есть какой то способ оптимизировать законно",
        "target_topic": "consulting_tax_overpayment_3101",
        "target_category": "pain_consulting",
        "pain_keywords": ["налог", "оптимиз", "нагрузк", "анализ"],
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _search_with_details(retriever, message: str):
    """Вызвать search и вернуть SearchResult со всеми деталями."""
    results = retriever.search(message, top_k=_PAIN_TOP_K)
    details = []
    for r in results:
        details.append({
            "topic": r.section.topic,
            "category": r.section.category,
            "score": round(r.score, 4),
            "stage": r.stage.value,
            "matched_keywords": r.matched_keywords,
            "facts_preview": r.section.facts.strip()[:200],
        })
    return details


def _check_pain_in_response(response: str, pain_keywords: List[str]) -> Dict:
    """Проверяем упоминание болевых решений в ответе бота."""
    resp_lower = response.lower()
    found = [kw for kw in pain_keywords if kw.lower() in resp_lower]
    return {
        "keywords_found_in_response": found,
        "match_count": len(found),
        "total_expected": len(pain_keywords),
    }


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------
def run_e2e():
    print("=" * 80)
    print("  PAIN RETRIEVAL E2E — 20 сообщений через полный автономный пайплайн")
    print("=" * 80)
    print()

    # --- Setup pipeline ---
    setup_autonomous_pipeline()
    llm = OllamaLLM()
    bot = SalesBot(llm=llm, flow_name="autonomous")

    # --- Get pain retriever ---
    pain_retriever = get_pain_retriever()
    has_embeddings = pain_retriever.use_embeddings and pain_retriever.embedder is not None
    pain_sections_count = len(pain_retriever.kb.sections)

    print(f"Pain KB: {pain_sections_count} секций")
    print(f"Embeddings: {'ON' if has_embeddings else 'OFF (keyword-only!)'}")
    print(f"LLM gate: {'ON' if llm else 'OFF'}")
    print()

    results = []
    passed = 0
    total = len(MESSAGES)

    for idx, scenario in enumerate(MESSAGES):
        msg_id = scenario["id"]
        user_msg = scenario["msg"]
        target_topic = scenario["target_topic"]
        target_category = scenario["target_category"]
        pain_keywords = scenario["pain_keywords"]

        print(f"{'─' * 80}")
        print(f"[{msg_id}] {user_msg}")
        print(f"  TARGET: {target_category}/{target_topic}")
        print()

        t0 = time.time()

        # === STEP 1: Pain search (isolated) ===
        search_results = _search_with_details(pain_retriever, user_msg)
        search_ms = (time.time() - t0) * 1000

        top_hit = search_results[0] if search_results else None
        topic_found = top_hit["topic"] if top_hit else None
        topic_match = topic_found == target_topic if top_hit else False
        # Relaxed: any result in target category
        category_hit = any(r["category"] == target_category for r in search_results)

        print(f"  STEP 1 — CascadeRetriever.search() [{search_ms:.0f}ms]")
        if not search_results:
            print(f"    -> ПУСТО (ничего не найдено)")
        for i, sr in enumerate(search_results):
            marker = "<<< TARGET" if sr["topic"] == target_topic else ""
            print(f"    [{i+1}] {sr['category']}/{sr['topic']}  score={sr['score']}  stage={sr['stage']}  {marker}")
            if sr["matched_keywords"]:
                print(f"        keywords: {sr['matched_keywords']}")
            print(f"        facts: {sr['facts_preview'][:120]}...")
        print()

        # === STEP 2: LLM pain gate ===
        t1 = time.time()
        gate_result = None
        if llm:
            gate_result = _llm_has_pain_signal(llm=llm, user_message=user_msg, intent=None)
        gate_ms = (time.time() - t1) * 1000

        gate_label = {True: "YES (боль)", False: "NO (не боль)", None: "N/A (не определил)"}
        print(f"  STEP 2 — LLM pain gate [{gate_ms:.0f}ms]: {gate_label.get(gate_result, '???')}")
        print()

        # === STEP 3: retrieve_pain_context (full) ===
        t2 = time.time()
        pain_ctx = retrieve_pain_context(user_msg, intent=None, llm=llm)
        ctx_ms = (time.time() - t2) * 1000
        pain_ctx_len = len(pain_ctx)

        print(f"  STEP 3 — retrieve_pain_context() [{ctx_ms:.0f}ms]: {pain_ctx_len} chars")
        if pain_ctx:
            # Show first 300 chars
            preview = pain_ctx.replace("\n", " \\n ")[:300]
            print(f"    -> {preview}")
        else:
            print(f"    -> ПУСТО (gate подавил или ничего не найдено)")
        print()

        # === STEP 4: Full pipeline (bot.process) ===
        # Reset bot for each message (fresh dialog)
        bot_fresh = SalesBot(llm=llm, flow_name="autonomous")

        # Warm-up greeting
        bot_fresh.process("здравствуйте, у меня магазин продуктов в алматы")

        t3 = time.time()
        result = bot_fresh.process(user_msg)
        pipeline_ms = (time.time() - t3) * 1000

        bot_response = result.get("response", "")
        classified_intent = result.get("intent", "???")
        current_state = result.get("state", "???")
        action = result.get("action", "???")

        print(f"  STEP 4 — bot.process() [{pipeline_ms:.0f}ms]")
        print(f"    intent:  {classified_intent}")
        print(f"    state:   {current_state}")
        print(f"    action:  {action}")
        print()

        # === STEP 5: Check pain integration in response ===
        pain_check = _check_pain_in_response(bot_response, pain_keywords)

        print(f"  STEP 5 — Ответ бота ({len(bot_response)} chars):")
        print(f"    {bot_response[:400]}")
        if len(bot_response) > 400:
            print(f"    ... (+{len(bot_response) - 400} chars)")
        print()

        # === STEP 6: Verdict ===
        # Pass if: pain_context non-empty AND (topic match or category hit)
        is_pass = pain_ctx_len > 0 and (topic_match or category_hit)

        verdict = "PASS" if is_pass else "FAIL"
        if is_pass:
            passed += 1

        issues = []
        if not search_results:
            issues.append("search вернул 0 результатов")
        elif not topic_match:
            issues.append(f"top-1 = {topic_found} (ожидался {target_topic})")
        if gate_result is False:
            issues.append("LLM gate = NO (подавил)")
        if pain_ctx_len == 0:
            issues.append("pain_context ПУСТ")
        if pain_check["match_count"] == 0:
            issues.append("ни одного pain-keyword в ответе бота")

        print(f"  [{verdict}] search_hits={len(search_results)} topic_match={topic_match} "
              f"category_hit={category_hit} gate={gate_result} "
              f"pain_ctx={pain_ctx_len}ch pain_kw_in_resp={pain_check['match_count']}/{pain_check['total_expected']}")
        if issues:
            print(f"    ISSUES: {'; '.join(issues)}")
        print()

        results.append({
            "id": msg_id,
            "message": user_msg,
            "target_topic": target_topic,
            "target_category": target_category,
            "search_results": search_results,
            "search_ms": round(search_ms, 1),
            "gate_result": gate_result,
            "gate_ms": round(gate_ms, 1),
            "pain_context_len": pain_ctx_len,
            "pain_context_preview": pain_ctx[:400] if pain_ctx else "",
            "ctx_ms": round(ctx_ms, 1),
            "classified_intent": classified_intent,
            "state": current_state,
            "action": action,
            "bot_response": bot_response,
            "pipeline_ms": round(pipeline_ms, 1),
            "pain_keywords_in_response": pain_check,
            "topic_match": topic_match,
            "category_hit": category_hit,
            "verdict": verdict,
            "issues": issues,
        })

    # ---------------------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------------------
    print("=" * 80)
    print(f"  ИТОГО: {passed}/{total} PASS")
    print("=" * 80)
    print()

    for r in results:
        icon = "OK" if r["verdict"] == "PASS" else "!!"
        top_hit_str = ""
        if r["search_results"]:
            top = r["search_results"][0]
            top_hit_str = f"top={top['topic']}({top['score']})"
        else:
            top_hit_str = "top=NONE"

        gate_str = {True: "YES", False: "NO", None: "N/A"}.get(r["gate_result"], "?")
        print(
            f"  [{icon}] {r['id']}  gate={gate_str}  ctx={r['pain_context_len']:>4}ch  "
            f"{top_hit_str}  match={'Y' if r['topic_match'] else 'N'}  "
            f"kw={r['pain_keywords_in_response']['match_count']}/{r['pain_keywords_in_response']['total_expected']}  "
            f"| {r['message'][:55]}"
        )
        if r["issues"]:
            print(f"       -> {'; '.join(r['issues'])}")

    # --- Save JSON ---
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path("results")
    out_dir.mkdir(exist_ok=True)
    out_json = out_dir / f"pain_retrieval_e2e_20_{ts}.json"

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": ts,
            "total": total,
            "passed": passed,
            "embeddings": has_embeddings,
            "pain_sections": pain_sections_count,
            "results": results,
        }, f, ensure_ascii=False, indent=2)

    print(f"\nJSON: {out_json}")


if __name__ == "__main__":
    run_e2e()
