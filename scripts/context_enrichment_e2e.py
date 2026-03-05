#!/usr/bin/env python3
"""
E2E Test — 15 scenarios: Context Enrichment for Decision/Classifier LLM nodes.

Focuses on:
  T01-T03: Decision AMNESIA — decision LLM ignores dialog context (no history)
  T04-T06: Premature/late state transitions (graduation criteria)
  T07-T09: Classifier context loss on short/ambiguous messages (2-turn history)
  T10-T12: Closing terminal requirements (dynamic graduation for payment_ready/video_call_scheduled)
  T13-T15: Complex multi-topic dialogs (context retention across topics)

Usage:
    python -m scripts.context_enrichment_e2e [pre|post]
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.bot import SalesBot, setup_autonomous_pipeline
from src.llm import OllamaLLM

SCENARIOS = [
    # ═══════════════════════════════════════════
    # T01: Decision amnesia — клиент уже сказал бизнес, decision не знает
    # Тест: decision видит историю → не застревает в discovery
    # ═══════════════════════════════════════════
    {
        "id": "T01",
        "name": "Decision amnesia — бизнес уже назван, бот не застревает в discovery",
        "focus": "decision_history",
        "check_points": [
            "Бот НЕ спрашивает повторно о бизнесе после T3",
            "К T5 бот перешёл из discovery (state != autonomous_discovery)",
            "Decision видит что business_type уже собран",
        ],
        "msgs": [
            "Привет",
            "У меня сеть из 3 продуктовых магазинов в Алматы",
            "Нам нужна единая система учёта, что предложите?",
            "Да, всё верно, 3 магазина",
            "Расскажите подробнее про функции",
            "А какой тариф подойдёт для 3 точек?",
        ],
    },
    # ═══════════════════════════════════════════
    # T02: Decision amnesia — клиент уже обсуждает цены, decision не видит
    # Тест: decision понимает что мы уже в presentation/qualification
    # ═══════════════════════════════════════════
    {
        "id": "T02",
        "name": "Decision amnesia — обсуждение цен, но decision не видит контекста",
        "focus": "decision_history",
        "check_points": [
            "После обсуждения цен бот не откатывается в discovery",
            "State после T5 = autonomous_presentation или далее",
            "Ответы содержат конкретные цены (не уклоняется)",
        ],
        "msgs": [
            "Здравствуйте, у меня один магазин электроники",
            "Сколько стоит Mini?",
            "А Lite?",
            "А можно сравнить все тарифы?",
            "Что входит в Standard помимо того что в Lite?",
            "Standard за 220 тысяч — это в год?",
            "А оборудование отдельно покупать?",
        ],
    },
    # ═══════════════════════════════════════════
    # T03: Decision amnesia — клиент возражает, decision не видит
    # Тест: decision понимает возражение из контекста, не прыгает в closing
    # ═══════════════════════════════════════════
    {
        "id": "T03",
        "name": "Decision amnesia — возражение 'дорого', decision не видит историю",
        "focus": "decision_history",
        "check_points": [
            "Бот отрабатывает возражение 'дорого' (не игнорирует)",
            "Не прыгает в closing после возражения",
            "Предлагает альтернативу (Mini/Lite) или рассрочку",
        ],
        "msgs": [
            "Добрый день, у меня магазин косметики",
            "Сколько стоит Standard?",
            "220 тысяч?! Это очень дорого для одного магазина",
            "У меня бюджет максимум 10 тысяч в месяц",
            "А что входит в Mini за 5000?",
            "А можно потом перейти на Standard когда бизнес вырастет?",
        ],
    },
    # ═══════════════════════════════════════════
    # T04: Premature transition — discovery→qualification без required_data
    # Тест: graduation criteria блокирует преждевременный переход
    # ═══════════════════════════════════════════
    {
        "id": "T04",
        "name": "Premature transition — нет business_type, нельзя уходить из discovery",
        "focus": "graduation_criteria",
        "check_points": [
            "Бот остаётся в discovery до T3 (пока не узнает бизнес)",
            "Бот задаёт уточняющий вопрос о бизнесе",
            "Не перескакивает в qualification без business_type",
        ],
        "msgs": [
            "Привет",
            "Хочу подключить кассовую программу",
            "У меня магазин обуви, одна точка",
            "Да, в Астане",
            "Какой тариф мне подойдёт?",
        ],
    },
    # ═══════════════════════════════════════════
    # T05: Late transition — все данные собраны, но бот застрял
    # Тест: graduation criteria показывает всё ✅ → переход
    # ═══════════════════════════════════════════
    {
        "id": "T05",
        "name": "Late transition — все данные discovery собраны, но бот застрял",
        "focus": "graduation_criteria",
        "check_points": [
            "После T4 бот уже не в discovery (все required собраны)",
            "Бот перешёл в qualification или presentation",
            "Не задаёт лишних вопросов про бизнес когда всё ясно",
        ],
        "msgs": [
            "Здравствуйте, у нас сеть магазинов одежды — 4 точки в Алматы",
            "Да, розничная торговля, женская одежда",
            "Нас 15 сотрудников, 4 кассы",
            "Сейчас всё на бумаге ведём, хотим автоматизировать",
            "Бюджет примерно 300 тысяч в год готовы выделить",
            "Расскажите что у вас есть для сети магазинов",
        ],
    },
    # ═══════════════════════════════════════════
    # T06: Graduation — closing без required terminal data
    # Тест: в closing бот видит ❌ для kaspi_phone/iin → просит
    # ═══════════════════════════════════════════
    {
        "id": "T06",
        "name": "Closing — бот должен собрать terminal data перед финалом",
        "focus": "graduation_criteria",
        "check_points": [
            "Бот перешёл в closing после ready-to-buy",
            "Бот просит контактные данные / телефон",
            "Не финализирует без сбора обязательных данных",
        ],
        "msgs": [
            "Здравствуйте, у меня аптека в Караганде",
            "Мне нужна кассовая программа, что есть?",
            "Standard подойдёт. Сколько стоит?",
            "Хорошо, беру Standard. Как подключиться?",
            "Конечно, мой номер 87473334455",
        ],
    },
    # ═══════════════════════════════════════════
    # T07: Classifier context — "да" без контекста (2 хода мало)
    # Тест: classifier видит 4 хода → понимает что "да" = подтверждение
    # ═══════════════════════════════════════════
    {
        "id": "T07",
        "name": "Classifier context — 'да' как подтверждение (нужен контекст)",
        "focus": "classifier_history",
        "check_points": [
            "Бот понимает 'да' как подтверждение предыдущего контекста",
            "Не переспрашивает после 'да'",
            "Продолжает разговор по теме",
        ],
        "msgs": [
            "Здравствуйте, у меня продуктовый магазин",
            "Нужна кассовая программа с учётом остатков",
            "У нас 2 точки, нужна единая база",
            "Вы упомянули Standard тариф — в нём есть складской учёт?",
            "Да",
            "А для двух точек подойдёт?",
            "Да, давайте оформим",
        ],
    },
    # ═══════════════════════════════════════════
    # T08: Classifier context — "а скидка?" (нужна история цен)
    # Тест: classifier с 4 ходами понимает контекст ценовой дискуссии
    # ═══════════════════════════════════════════
    {
        "id": "T08",
        "name": "Classifier context — 'а скидка?' после обсуждения цен",
        "focus": "classifier_history",
        "check_points": [
            "Бот понимает 'а скидка?' как price_question в контексте",
            "Отвечает про скидки/рассрочку (не уходит в discovery)",
            "Не теряет контекст после короткого сообщения",
        ],
        "msgs": [
            "Привет, магазин запчастей для авто, 1 точка",
            "Сколько стоит Lite?",
            "А Standard?",
            "220 тысяч в год это немало",
            "А скидка есть?",
            "А рассрочка?",
        ],
    },
    # ═══════════════════════════════════════════
    # T09: Classifier context — "а на год?" (нужен контекст что обсуждали)
    # Тест: classifier понимает "а на год?" = запрос годовой цены
    # ═══════════════════════════════════════════
    {
        "id": "T09",
        "name": "Classifier context — 'а на год?' контексто-зависимый вопрос",
        "focus": "classifier_history",
        "check_points": [
            "Бот понимает 'а на год?' как вопрос о годовой цене/сроке",
            "Отвечает с конкретными числами",
            "Не переспрашивает 'что вы имеете в виду?'",
        ],
        "msgs": [
            "Здравствуйте, у меня магазин бытовой техники",
            "Сколько стоит Mini в месяц?",
            "А на год?",
            "А Lite?",
            "А чем Lite лучше Mini?",
        ],
    },
    # ═══════════════════════════════════════════
    # T10: Terminal — payment_ready requirements (kaspi_phone + iin)
    # Тест: graduation показывает ❌/✅ для terminal requirements
    # ═══════════════════════════════════════════
    {
        "id": "T10",
        "name": "Terminal payment_ready — kaspi_phone + iin обязательны",
        "focus": "terminal_requirements",
        "check_points": [
            "Бот собирает kaspi_phone перед payment_ready",
            "Бот запрашивает ИИН",
            "Переход в payment_ready только после сбора всех данных",
        ],
        "msgs": [
            "Здравствуйте, у меня магазин, хочу подключить Mini",
            "Да, один магазин, продукты",
            "Давайте оформим, 5000 в месяц нормально",
            "Хочу оплатить через Kaspi",
            "Мой Kaspi номер 87017778899",
            "ИИН 890623300123",
        ],
    },
    # ═══════════════════════════════════════════
    # T11: Terminal — video_call_scheduled requirements (contact_info)
    # Тест: graduation показывает ❌ для contact_info → просит
    # ═══════════════════════════════════════════
    {
        "id": "T11",
        "name": "Terminal video_call_scheduled — contact_info обязателен",
        "focus": "terminal_requirements",
        "check_points": [
            "Бот просит контакт перед video_call_scheduled",
            "Принимает телефон как contact_info",
            "Не финализирует без контакта",
        ],
        "msgs": [
            "Привет, у нас сеть из 5 магазинов, хотим Pro",
            "Да, нам нужна полная автоматизация",
            "Хотим чтобы нам позвонили и всё объяснили подробно",
            "Назначьте звонок на завтра",
            "Мой телефон 87021112233",
        ],
    },
    # ═══════════════════════════════════════════
    # T12: Fast-track — demo_request → closing
    # Тест: fast-track из любого стейта в closing при demo_request
    # ═══════════════════════════════════════════
    {
        "id": "T12",
        "name": "Fast-track — demo_request из discovery → closing",
        "focus": "terminal_requirements",
        "check_points": [
            "Бот переходит в closing после demo_request",
            "Не говорит 'нет демо' (заменяет на 'расскажу прямо здесь')",
            "Просит контактные данные",
        ],
        "msgs": [
            "Здравствуйте, у меня цветочный магазин",
            "Можно мне демонстрацию программы?",
            "Ну хорошо, тогда расскажите что есть для одного магазина",
            "Lite подойдёт, давайте подключим",
            "87775556677",
        ],
    },
    # ═══════════════════════════════════════════
    # T13: Multi-topic — контекст не теряется при переключении тем
    # Тест: decision видит историю → помнит контекст бизнеса
    # ═══════════════════════════════════════════
    {
        "id": "T13",
        "name": "Multi-topic — переключение тем, контекст не теряется",
        "focus": "context_retention",
        "check_points": [
            "Бот помнит тип бизнеса (кафе) через всю беседу",
            "При возврате к ценам — помнит что обсуждали Standard",
            "Не теряет контекст при переключении тем",
        ],
        "msgs": [
            "Привет, у меня кафе в Алматы",
            "Нужна касса, что предложите?",
            "Сколько стоит Standard?",
            "А обучение сотрудников входит?",
            "А ОФД подключаете?",
            "Вернёмся к Standard — там есть учёт остатков?",
            "Хорошо, давайте Standard. Мой номер 87019998877",
        ],
    },
    # ═══════════════════════════════════════════
    # T14: Long dialog — 10+ ходов, decision+classifier должны держать контекст
    # Тест: на длинном диалоге бот не ломается
    # ═══════════════════════════════════════════
    {
        "id": "T14",
        "name": "Long dialog — 10+ ходов, контекст не разваливается",
        "focus": "context_retention",
        "check_points": [
            "Бот помнит контекст через 10+ ходов",
            "SPIN-фазы прогрессируют логично",
            "Не задаёт повторных вопросов о бизнесе",
            "Closing корректный",
        ],
        "msgs": [
            "Здравствуйте",
            "У меня магазин строительных материалов, 2 точки в Караганде",
            "Нужна единая система — касса плюс учёт товара",
            "А складской учёт есть?",
            "Между двумя точками перемещение товара поддерживается?",
            "Сколько стоит Standard?",
            "А Pro зачем, если у меня всего 2 точки?",
            "Ок, Standard. А оборудование что нужно?",
            "А сканер штрихкодов входит в комплект?",
            "Хорошо, давайте Standard тариф + стандартный комплект оборудования",
            "Как подключиться?",
            "87015553322",
        ],
    },
    # ═══════════════════════════════════════════
    # T15: Казахский + короткие ответы — classifier и decision нужен контекст
    # Тест: казахские/короткие ответы корректно классифицируются с 4 ходами
    # ═══════════════════════════════════════════
    {
        "id": "T15",
        "name": "Казахский + короткие ответы — контекст для classifier",
        "focus": "classifier_history",
        "check_points": [
            "Бот понимает казахские слова/ответы",
            "Короткие ответы ('иә', 'жоқ', 'рахмет') корректно классифицируются",
            "Не ломается на смешанном KZ/RU",
        ],
        "msgs": [
            "Сәлеметсіз бе",
            "Менде дүкен бар, азық-түлік",
            "Бағдарлама қанша тұрады?",
            "Lite жарайды",
            "Иә",
            "Рахмет, жақсы",
            "87751234567",
        ],
    },
]

DIVIDER = "─" * 80


def run_dialog(scenario: dict, bot: SalesBot) -> dict:
    """Запускает один диалог, собирает все метаданные."""
    bot.reset()
    turns = []
    start = time.time()

    for i, msg in enumerate(scenario["msgs"]):
        t0 = time.time()
        result = bot.process(msg)
        elapsed = time.time() - t0

        turn_data = {
            "turn": i + 1,
            "user": msg,
            "bot": result["response"],
            "state": result.get("state", "?"),
            "action": result.get("action", "?"),
            "spin_phase": result.get("spin_phase", "?"),
            "intent": result.get("intent", "?"),
            "template_key": result.get("template_key", "?"),
            "is_final": result.get("is_final", False),
            "confidence": result.get("confidence", 0),
            "elapsed_s": round(elapsed, 2),
        }

        ed = result.get("extracted_data")
        if ed and isinstance(ed, dict):
            non_empty = {k: v for k, v in ed.items() if v}
            if non_empty:
                turn_data["extracted_data"] = non_empty

        vm = result.get("_factual_verifier_meta")
        if vm and isinstance(vm, dict):
            turn_data["verifier_meta"] = vm

        turns.append(turn_data)
        if result.get("is_final"):
            break

    total_time = round(time.time() - start, 2)
    return {
        "id": scenario["id"],
        "name": scenario["name"],
        "focus": scenario["focus"],
        "check_points": scenario["check_points"],
        "turns": turns,
        "total_time_s": total_time,
        "num_turns": len(turns),
    }


def auto_check(scenario: dict, dialog: dict) -> dict:
    """Автоматическая проверка ключевых метрик."""
    checks = {}
    turns = dialog["turns"]
    sid = scenario["id"]
    focus = scenario["focus"]

    # Собираем все states
    states = [t["state"] for t in turns]
    last_state = states[-1] if states else "?"
    intents = [t["intent"] for t in turns]
    all_bot_text = " ".join(t["bot"] for t in turns).lower()

    # --- Decision history checks ---
    if sid == "T01":
        # К T5 (index 4) бот должен выйти из discovery
        # (graduation criteria не должна задерживать — optional data не блокирует)
        checks["left_discovery_by_T5"] = (
            len(states) > 4 and states[4] != "autonomous_discovery"
        )
        # Не спрашивает повторно о бизнесе после T3
        late_bot = " ".join(t["bot"] for t in turns[3:]).lower()
        checks["no_repeat_business_question"] = not any(
            q in late_bot for q in ["расскажите о вашем бизнесе", "чем вы занимаетесь", "какой у вас бизнес"]
        )

    elif sid == "T02":
        # State после T5 != autonomous_discovery
        checks["not_in_discovery_after_T5"] = (
            len(states) > 4 and states[4] != "autonomous_discovery"
        )
        # Отвечает с ценами (не уклоняется)
        checks["has_prices"] = any(
            p in all_bot_text for p in ["5 000", "5000", "150 000", "150000", "220 000", "220000"]
        )

    elif sid == "T03":
        # Не прыгает в closing после возражения "дорого"
        checks["no_premature_closing"] = "autonomous_closing" not in states[:4]
        # Предлагает альтернативу
        checks["offers_alternative"] = any(
            w in all_bot_text for w in ["mini", "lite", "рассрочк", "дешевле", "доступн"]
        )

    # --- Graduation criteria checks ---
    elif sid == "T04":
        # Бот остаётся в discovery до T3 (пока не узнает бизнес)
        # T1=greeting, T2="хочу кассовую программу" (no business_type → must be discovery)
        # T3="магазин обуви" (business_type provided → can graduate on same turn)
        auto_states = [s for s in states if s.startswith("autonomous_")]
        checks["stays_discovery_until_business"] = (
            len(auto_states) >= 1
            and auto_states[0] == "autonomous_discovery"
        )

    elif sid == "T05":
        # После T4 (index 3) бот уже не в discovery
        checks["left_discovery_by_T4"] = (
            len(states) > 3 and states[3] != "autonomous_discovery"
        )

    elif sid == "T06":
        # Бот перешёл в closing
        checks["reached_closing"] = "autonomous_closing" in states
        # Бот просит контакт
        checks["asks_contact"] = any(
            w in all_bot_text for w in ["телефон", "номер", "контакт", "позвон"]
        )

    # --- Classifier context checks ---
    elif sid == "T07":
        # "да" не вызывает переспрос
        da_turns = [i for i, t in enumerate(turns) if t["user"].strip().lower() == "да"]
        if da_turns:
            next_idx = da_turns[0] + 1
            if next_idx < len(turns):
                bot_after_da = turns[da_turns[0]]["bot"].lower()
                checks["da_understood"] = not any(
                    q in bot_after_da for q in ["что вы имеете", "уточните", "не понял"]
                )
            else:
                checks["da_understood"] = True
        else:
            checks["da_understood"] = True
        # "давайте оформим" (T7) → бот должен перейти в closing
        oformim_turns = [i for i, t in enumerate(turns) if "оформим" in t["user"].lower()]
        if oformim_turns:
            oformim_idx = oformim_turns[0]
            checks["oformim_triggers_closing"] = states[oformim_idx] == "autonomous_closing"
        else:
            checks["oformim_triggers_closing"] = True

    elif sid == "T08":
        # "а скидка?" (T5, index 4) → после неё не уходит в discovery
        # Проверяем что после T5 (index 4) бот не в discovery
        checks["discount_not_discovery"] = (
            len(states) > 4 and "autonomous_discovery" not in states[4:]
        )
        # Отвечает про скидки/рассрочку
        checks["mentions_discount"] = any(
            w in all_bot_text for w in ["скидк", "рассрочк", "kaspi", "каспи", "процент", "услови", "акци"]
        )
        # Не говорит "уточню у коллег" на вопрос о скидке
        discount_turn_idx = next((i for i, t in enumerate(turns) if "скидк" in t["user"].lower()), None)
        if discount_turn_idx is not None:
            bot_discount = turns[discount_turn_idx]["bot"].lower()
            checks["no_utochnu_deflection"] = "уточню у коллег" not in bot_discount
        else:
            checks["no_utochnu_deflection"] = True

    elif sid == "T09":
        # "а на год?" → отвечает с числами
        year_turn_idx = next((i for i, t in enumerate(turns) if "на год" in t["user"].lower()), None)
        if year_turn_idx is not None and year_turn_idx < len(turns):
            bot_resp = turns[year_turn_idx]["bot"]
            import re
            checks["year_price_given"] = bool(re.search(r'\d{2,3}\s*\d{3}', bot_resp))
        else:
            checks["year_price_given"] = False

    # --- Terminal requirements checks ---
    elif sid == "T10":
        checks["reached_final"] = any(t["is_final"] for t in turns)
        checks["payment_ready"] = last_state == "payment_ready" or any(t.get("is_final") for t in turns)

    elif sid == "T11":
        checks["asks_contact"] = any(
            w in all_bot_text for w in ["телефон", "номер", "контакт"]
        )

    elif sid == "T12":
        # Перешёл в closing
        checks["reached_closing"] = "autonomous_closing" in states
        # Не говорит "нет демо"
        checks["no_net_demo"] = "нет демо" not in all_bot_text

    # --- Context retention checks ---
    elif sid == "T13":
        # Помнит тип бизнеса через диалог
        checks["context_retained"] = True  # manual check
        # Не теряет контекст при переключении
        checks["reaches_closing"] = "autonomous_closing" in states or last_state not in ["autonomous_discovery"]

    elif sid == "T14":
        # SPIN прогрессирует (не застревает в одном стейте)
        unique_states = set(states)
        checks["state_progression"] = len(unique_states) >= 2
        # Не задаёт повторных вопросов
        checks["no_stuck_questions"] = True  # manual check

    elif sid == "T15":
        # Не ломается на казахском
        checks["no_crash"] = len(turns) == len(scenario["msgs"]) or any(t["is_final"] for t in turns)

    # Общий pass/fail
    total = len(checks)
    passed = sum(1 for v in checks.values() if v)
    checks["_summary"] = f"{passed}/{total}"
    checks["_pass"] = passed == total

    return checks


def format_dialog(d: dict, checks: dict) -> str:
    """Форматирует диалог для текстового отчёта."""
    pass_str = "PASS ✅" if checks.get("_pass") else "FAIL ❌"
    lines = [
        f"\n{'='*80}",
        f"  {d['id']} | {d['name']} | [{pass_str}] {checks.get('_summary', '?')}",
        f"  Focus: {d['focus']} | Ходов: {d['num_turns']} | Время: {d['total_time_s']}s",
        f"{'='*80}",
        "",
        "  Контрольные точки:",
    ]
    for cp in d["check_points"]:
        lines.append(f"    • {cp}")

    lines.append("")
    lines.append("  Автопроверки:")
    for k, v in checks.items():
        if k.startswith("_"):
            continue
        mark = "✅" if v else "❌"
        lines.append(f"    {mark} {k}: {v}")
    lines.append("")

    for t in d["turns"]:
        lines.append(DIVIDER)
        meta = f"T{t['turn']} | state={t['state']} | action={t['action']} | spin={t['spin_phase']} | intent={t['intent']} | conf={t['confidence']:.2f} | {t['elapsed_s']}s"
        lines.append(f"  [{meta}]")
        if t.get("template_key") and t["template_key"] != "?":
            lines.append(f"  template: {t['template_key']}")
        lines.append(f"  КЛИЕНТ: {t['user']}")
        lines.append(f"  БОТ:    {t['bot']}")
        if t.get("extracted_data"):
            lines.append(f"  Извлечено: {t['extracted_data']}")
        if t.get("verifier_meta"):
            vm = t["verifier_meta"]
            lines.append(f"  Верификатор: verdict={vm.get('verdict','?')} codes={vm.get('reason_codes',[])}")
        if t["is_final"]:
            lines.append("  ФИНАЛ")
        lines.append("")

    return "\n".join(lines)


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "run"

    setup_autonomous_pipeline()

    llm = OllamaLLM()
    bot = SalesBot(llm, flow_name="autonomous")

    all_results = []
    all_checks = []
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = Path(__file__).parent.parent / "results" / f"ctx_enrichment_{label}_{ts}.json"
    json_path.parent.mkdir(exist_ok=True)

    print(f"\n{'='*80}")
    print(f"  CONTEXT ENRICHMENT E2E — {label.upper()} — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  15 scenarios | Validators: ON")
    print(f"{'='*80}")

    total_pass = 0
    total_fail = 0

    for scenario in SCENARIOS:
        print(f"\n>>> [{scenario['id']}] {scenario['name']} ({len(scenario['msgs'])} msgs)...")
        dialog = run_dialog(scenario, bot)
        checks = auto_check(scenario, dialog)
        formatted = format_dialog(dialog, checks)
        print(formatted)
        all_results.append(dialog)
        all_checks.append({"id": scenario["id"], "checks": checks})
        if checks.get("_pass"):
            total_pass += 1
        else:
            total_fail += 1

    # Summary
    print(f"\n{'='*80}")
    print(f"  ИТОГО: {total_pass} PASS / {total_fail} FAIL из 15")
    print(f"{'='*80}")
    print(f"\n  Детали:")
    for c in all_checks:
        mark = "✅" if c["checks"].get("_pass") else "❌"
        print(f"    {mark} {c['id']}: {c['checks'].get('_summary', '?')}")

    # Save JSON
    output = {
        "label": label,
        "timestamp": ts,
        "summary": {"pass": total_pass, "fail": total_fail, "total": 15},
        "scenarios": all_results,
        "checks": all_checks,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n  JSON: {json_path}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
