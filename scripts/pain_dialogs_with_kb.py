#!/usr/bin/env python3
"""
Прогон 10 реалистичных диалогов с захватом retrieved_facts + pain_context.
Выход: чистый текстовый файл с цитатами из БЗ рядом с каждым ответом бота.

Запуск:
    python -m scripts.pain_dialogs_with_kb 2>/dev/null
"""

import sys
import time
import re
from pathlib import Path
from typing import List, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.bot import SalesBot, setup_autonomous_pipeline
from src.llm import OllamaLLM
from src.knowledge.pain_retriever import retrieve_pain_context

SCENARIOS: List[Dict[str, Any]] = [
    {
        "id": "D01", "name": "Касса тупит + цена в одном сообщении",
        "msgs": [
            "салам, мне друг посоветовал вас глянуть",
            "у нас 2 магазина продуктов в караганде",
            "ну мне тут сказали посмотреть, у нас касса иногда тупит при наплыве людей, а сколько стоит вообще ваша система?",
            "ну если тормозить не будет то может и возьмем",
        ],
    },
    {
        "id": "D02", "name": "Сканер + сколько точек + бюджет",
        "msgs": [
            "здравствуйте хочу узнать про вашу систему",
            "у нас аптека, 1 точка, примерно 3000 позиций",
            "главная проблема — сканер по 5 раз проводишь пока считает, клиенты психуют, и еще вопрос у вас рассрочка есть?",
            "ладно а маркировку поддерживаете? у нас же лекарства",
        ],
    },
    {
        "id": "D03", "name": "Боль в возражении на цену",
        "msgs": [
            "привет, мне нужна касса для магазина одежды",
            "а сколько стоит на 1 точку?",
            "дороговато если честно, я щас вручную в тетрадке все веду и товар добавляю по 2 часа каждую поставку, но все равно дорого",
            "ну а если на год то скидка есть какая нибудь?",
        ],
    },
    {
        "id": "D04", "name": "СНР страх спрятан в общем вопросе",
        "msgs": [
            "добрый день, я ип, розничная торговля",
            "слушайте а у вас есть что нибудь для учета налогов? мне бухгалтер сказала что с 2026 какие то изменения по снр и если не подготовимся то на общий режим переведут, я вообще в этом не разбираюсь",
            "а это прям автоматически все считает? я боюсь что штраф выпишут",
            "ну и сколько это стоит тогда",
        ],
    },
    {
        "id": "D05", "name": "Кража кассира + недоверие",
        "msgs": [
            "здрасте я ищу программу для магазина",
            "продукты, 1 точка, алматы, 5 сотрудников",
            "у нас тут проблема — подозреваю что кассирша ворует, удаляет позиции из чека а деньги себе, но доказать не могу потому что система ничего не логирует. вы это решаете?",
            "а она не сможет как нибудь обойти вашу систему?",
        ],
    },
    {
        "id": "D06", "name": "Ревизия + конкурент",
        "msgs": [
            "мы сейчас на 1с сидим но думаем переехать",
            "основная причина — ревизия у нас 2 дня занимает каждый месяц, все вручную считаем, это капец. 1с вообще не помогает. у вас быстрее?",
            "а данные с 1с можно перенести к вам?",
            "ну и чо по цене на 3 точки",
        ],
    },
    {
        "id": "D07", "name": "Принтер сдох + уже злой",
        "msgs": [
            "вы продаете кассовое оборудование?",
            "короче у нас принтер чеков сдох вчера прям в самый час пик, мы полдня не торговали из за этого, продавцы на телефон чеки скидывали, бред. нужен нормальный принтер который не сломается через месяц, и желательно побыстрее доставить",
            "а гарантия на него какая?",
        ],
    },
    {
        "id": "D08", "name": "Бухгалтер ушел + 910 форма",
        "msgs": [
            "добрый день",
            "у меня тоо, оптовая торговля, 15 человек в штате",
            "короче у нас бухгалтер уволился месяц назад, 910 форму скоро сдавать а мы вообще не понимаем как, учет весь в голове у нее был. есть у вас какой то сервис бухгалтерский?",
            "а сколько стоит ваш аутсорсинг бухгалтерии?",
        ],
    },
    {
        "id": "D09", "name": "Электронный чек — боль внутри разговора о фичах",
        "msgs": [
            "привет, расскажите что умеет ваша система",
            "нас интересует управление товарами и складом",
            "а еще вопрос — у нас клиенты постоянно просят чек на вотсап или на почту а мы не можем, только бумажный, это прям стыдно уже. это у вас есть?",
            "круто, а сколько стоит подключение?",
        ],
    },
    {
        "id": "D10", "name": "Негатив без явной боли -> потом боль на 4 ходу",
        "msgs": [
            "здравствуйте",
            "мне нужна программа для автоматизации магазина стройматериалов",
            "3 точки, астана, каждый день по 200-300 чеков",
            "а вот еще вопрос, мы скоро наверно лимит по мрп превысим, оборот растет быстро, я боюсь что автоматом на ндс переведут. ваша система как то предупреждает об этом?",
            "ну если предупреждает то хорошо, а сколько стоит на 3 точки?",
        ],
    },
]


def extract_kb_snippet(facts: str, max_len: int = 400) -> str:
    """Extract meaningful KB snippet, strip headers and noise."""
    if not facts or not facts.strip():
        return ""
    lines = facts.split("\n")
    useful = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        # Skip section headers like [pricing/pricing_standard]
        if re.match(r'^\[.+/.+\]$', s):
            continue
        # Skip === separators
        if s.startswith("===") and s.endswith("==="):
            continue
        # Skip "topic:", "priority:", "keywords:" metadata
        if re.match(r'^(topic|priority|keywords|category)\s*:', s):
            continue
        # Skip "response_context empty"
        if "response_context" in s.lower() and "empty" in s.lower():
            continue
        useful.append(s)
    text = " ".join(useful)
    if len(text) > max_len:
        text = text[:max_len] + "..."
    return text


def extract_pain_snippet(pain_ctx: str, max_len: int = 300) -> str:
    """Extract pain KB snippet, strip instruction headers."""
    if not pain_ctx or not pain_ctx.strip():
        return ""
    lines = pain_ctx.split("\n")
    useful = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith("==="):
            continue
        if "вплети" in s.lower() or "не выделяй" in s.lower():
            continue
        if re.match(r'^\[.+/.+\]$', s):
            # Keep pain section headers but clean them
            useful.append(s)
            continue
        useful.append(s)
    text = " ".join(useful)
    if len(text) > max_len:
        text = text[:max_len] + "..."
    return text


def run():
    print("Running 10 dialogs with KB trace...", flush=True)

    setup_autonomous_pipeline()
    llm = OllamaLLM()

    out_lines = []
    out_lines.append("PAIN REALISTIC E2E — 10 диалогов с цитатами из БЗ")
    out_lines.append("Дата: 20260305")
    out_lines.append("")

    for scenario in SCENARIOS:
        sid = scenario["id"]
        name = scenario["name"]
        msgs = scenario["msgs"]

        print(f"\n{'='*60}", flush=True)
        print(f"  [{sid}] {name}", flush=True)

        out_lines.append("=" * 70)
        out_lines.append(f"[{sid}] {name}")
        out_lines.append("=" * 70)
        out_lines.append("")

        bot = SalesBot(llm=llm, flow_name="autonomous")

        # Monkey-patch generator to capture retrieved_facts
        gen = bot._generator if hasattr(bot, '_generator') else None
        if gen is None:
            # Try to get from orchestrator
            orch = getattr(bot, '_orchestrator', None) or getattr(bot, 'orchestrator', None)
            if orch:
                gen = getattr(orch, '_generator', None) or getattr(orch, 'generator', None)

        for i, msg in enumerate(msgs):
            t0 = time.time()

            # Get pain context (isolated)
            try:
                pain_ctx = retrieve_pain_context(msg, intent=None, llm=llm)
            except Exception:
                pain_ctx = ""

            # Full pipeline
            result = bot.process(msg)
            elapsed = (time.time() - t0) * 1000

            bot_resp = result.get("response", "")
            retrieved = result.get("retrieved_facts", "")

            # Try to get retrieved_facts from generation meta
            if not retrieved and gen:
                meta = getattr(gen, '_last_generation_meta', {})
                retrieved = meta.get("retrieved_facts", "")

            # Also try from result dict directly
            if not retrieved:
                retrieved = result.get("facts", "") or result.get("kb_facts", "")

            print(f"  ход {i+1}: {msg[:60]}... [{elapsed:.0f}ms]", flush=True)

            # Format output
            out_lines.append(f"Клиент: {msg}")

            # Add KB citations
            kb_snippet = extract_kb_snippet(retrieved)
            pain_snippet = extract_pain_snippet(pain_ctx)

            if kb_snippet or pain_snippet:
                out_lines.append("")
                if kb_snippet:
                    out_lines.append(f"    [БЗ] {kb_snippet}")
                if pain_snippet:
                    out_lines.append(f"    [БЗ боли] {pain_snippet}")
                out_lines.append("")

            out_lines.append(f"Бот: {bot_resp}")
            out_lines.append("")

        out_lines.append("")

    # Write output
    out_path = Path("results/pain_realistic_dialogs.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines))

    print(f"\nГотово: {out_path}", flush=True)


if __name__ == "__main__":
    run()
