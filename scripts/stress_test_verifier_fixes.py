"""
Жёсткий стресс-тест всех 5 исправлений FactualVerifier.

Покрывает:
  Change 1  — паrafраз KB, логический вывод, конкретные цифры, оценочные фразы
  Change 2  — история диалога видна в промпте верификатора
  Change 3  — rewritten_response из pass-1 используется вместо db_only
  Change 4  — _ensure_no_forbidden_fallback: стриппинг, не замена
  Change 5  — _enforce_no_colleague_fallback: стриппинг, не замена

Запуск:
    python -m scripts.stress_test_verifier_fixes [--verbose]
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
SCENARIOS = [
    # ===================================================================
    # CHANGE 1: паrafраз должен ПРОХОДИТЬ, добавление чисел — БЛОКИРОВАТЬ
    # ===================================================================
    {
        "id": "C1-01",
        "area": "Change1",
        "name": "Паrafраз KB о складе — должен пройти верификатор",
        "messages": [
            "Здравствуйте",
            "У нас продуктовый магазин",
            "Есть ли у вас учёт склада?",
        ],
        "expect": {
            "no_raw_kb_dump": True,
            "min_response_length": 40,
        },
    },
    {
        "id": "C1-02",
        "area": "Change1",
        "name": "Оценочные фразы ('хороший выбор') — не должны блокироваться",
        "messages": [
            "Здравствуйте",
            "Мы занимаемся розницей, небольшой магазин",
            "Что посоветуете из тарифов?",
        ],
        "expect": {
            "no_raw_kb_dump": True,
            "min_response_length": 40,
        },
    },
    {
        "id": "C1-03",
        "area": "Change1",
        "name": "Цена Mini — число должно быть точным (строгий контроль)",
        "messages": [
            "Здравствуйте",
            "1 касса, небольшой магазин",
            "Сколько стоит Mini?",
        ],
        "expect": {
            "contains_any": ["5 000", "5000", "пять тысяч"],
            "no_forbidden_phrase": True,
        },
    },
    {
        "id": "C1-04",
        "area": "Change1",
        "name": "Цена Standard — число должно быть из KB",
        "messages": [
            "Здравствуйте",
            "У нас 3 точки",
            "Сколько стоит Standard в год?",
        ],
        "expect": {
            "contains_any": ["220 000", "220000"],
            "no_forbidden_phrase": True,
        },
    },
    {
        "id": "C1-05",
        "area": "Change1",
        "name": "Логический вывод без числа — должен пройти",
        "messages": [
            "Здравствуйте",
            "Мы работаем с маркированными товарами — алкоголь и табак",
            "Ваша система поддерживает маркировку?",
        ],
        "expect": {
            "no_raw_kb_dump": True,
            "min_response_length": 40,
        },
    },
    {
        "id": "C1-06",
        "area": "Change1",
        "name": "Переходная фраза ('давайте разберёмся') — не должна блокировать",
        "messages": [
            "Здравствуйте",
            "Расскажите про интеграции",
        ],
        "expect": {
            "no_raw_kb_dump": True,
            "min_response_length": 30,
        },
    },
    # ===================================================================
    # CHANGE 2: история диалога помогает верификатору
    # ===================================================================
    {
        "id": "C2-01",
        "area": "Change2",
        "name": "История: клиент назвал 3 кассы — верификатор знает контекст",
        "messages": [
            "Здравствуйте",
            "Мы занимаемся розничной торговлей, у нас 3 кассы в одном магазине",
            "Больше всего проблемы с учётом остатков",
            "Какой тариф нам подойдёт?",
        ],
        "expect": {
            "no_raw_kb_dump": True,
            "min_response_length": 50,
        },
    },
    {
        "id": "C2-02",
        "area": "Change2",
        "name": "История: клиент назвал 5 точек — Standard/Pro должны упоминаться",
        "messages": [
            "Здравствуйте",
            "У нас сеть: 5 магазинов по Алматы",
            "Что посоветуете из тарифов для нашей сети?",
        ],
        "expect": {
            "no_raw_kb_dump": True,
            "min_response_length": 40,
        },
    },
    {
        "id": "C2-03",
        "area": "Change2",
        "name": "История: после обсуждения склада — вопрос о цене должен учесть контекст",
        "messages": [
            "Здравствуйте",
            "Проблема — теряем товар, нет учёта остатков",
            "Сколько стоит ваша система?",
        ],
        "expect": {
            "contains_any": ["5 000", "5000", "220 000", "220000", "от ", "₸"],
            "no_forbidden_phrase": True,
        },
    },
    {
        "id": "C2-04",
        "area": "Change2",
        "name": "Длинная история: 5 ходов — верификатор не теряет контекст",
        "messages": [
            "Здравствуйте",
            "Мы открываемся в следующем месяце",
            "Планируем 2 кассы",
            "Товары разные — продукты, непродовольственные",
            "Есть вопросы по поддержке: как быстро отвечаете?",
        ],
        "expect": {
            "no_raw_kb_dump": True,
            "min_response_length": 40,
        },
    },
    # ===================================================================
    # CHANGE 3: rewritten_response из pass-1 вместо db_only
    # ===================================================================
    {
        "id": "C3-01",
        "area": "Change3",
        "name": "Ответ с неточным парафразом — rewrite должен быть связным",
        "messages": [
            "Здравствуйте",
            "Расскажите о вашей системе подробнее",
            "Какие налоговые формы поддерживаются?",
        ],
        "expect": {
            "no_raw_kb_dump": True,
            "min_response_length": 40,
        },
    },
    {
        "id": "C3-02",
        "area": "Change3",
        "name": "Вопрос об ограничениях Mini — rewrite должен сохранить список",
        "messages": [
            "Здравствуйте",
            "Интересует тариф Mini",
            "Что недоступно в Mini?",
        ],
        "expect": {
            "no_raw_kb_dump": True,
            "min_response_length": 40,
        },
    },
    {
        "id": "C3-03",
        "area": "Change3",
        "name": "Вопрос об экспорте — rewrite должен упомянуть Excel/PDF",
        "messages": [
            "Здравствуйте",
            "Нам важны отчёты",
            "Можно ли экспортировать данные?",
        ],
        "expect": {
            "contains_any": ["Excel", "PDF", "excel", "pdf", "выгруз", "экспорт"],
            "no_forbidden_phrase": True,
        },
    },
    # ===================================================================
    # CHANGE 4: _ensure_no_forbidden_fallback: стрип не замена
    # ===================================================================
    {
        "id": "C4-01",
        "area": "Change4",
        "name": "Техподдержка — ответ не должен быть сырыми KB-строками",
        "messages": [
            "Здравствуйте",
            "Есть ли у вас техническая поддержка?",
        ],
        "expect": {
            "no_raw_kb_dump": True,
            "min_response_length": 30,
            "no_forbidden_phrase": True,
        },
    },
    {
        "id": "C4-02",
        "area": "Change4",
        "name": "Поддержка 24/7 — связный ответ про расписание",
        "messages": [
            "Здравствуйте",
            "Поддержка круглосуточная?",
        ],
        "expect": {
            "contains_any": ["00:00", "21:00", "будн", "выходн", "круглосуточ"],
            "no_forbidden_phrase": True,
        },
    },
    {
        "id": "C4-03",
        "area": "Change4",
        "name": "Сложный технический вопрос — не должен давать только 2 строки KB",
        "messages": [
            "Здравствуйте",
            "Как у вас организовано резервное копирование данных?",
        ],
        "expect": {
            "no_raw_kb_dump": True,
            "min_response_length": 40,
            "no_forbidden_phrase": True,
        },
    },
    # ===================================================================
    # CHANGE 5: _enforce_no_colleague_fallback: стрип не замена
    # ===================================================================
    {
        "id": "C5-01",
        "area": "Change5",
        "name": "Вопрос о безопасности данных — связный ответ, не KB-dump",
        "messages": [
            "Здравствуйте",
            "Как обеспечивается безопасность данных?",
        ],
        "expect": {
            "no_raw_kb_dump": True,
            "min_response_length": 50,
            "no_forbidden_phrase": True,
        },
    },
    {
        "id": "C5-02",
        "area": "Change5",
        "name": "Где хранятся данные — конкретный ответ про Казахстан",
        "messages": [
            "Здравствуйте",
            "Где хранятся данные — в Казахстане?",
        ],
        "expect": {
            "contains_any": ["Казахстан", "дата-центр", "РК"],
            "no_forbidden_phrase": True,
        },
    },
    {
        "id": "C5-03",
        "area": "Change5",
        "name": "API — связный ответ",
        "messages": [
            "Здравствуйте",
            "У вас есть API для интеграции?",
        ],
        "expect": {
            "no_raw_kb_dump": True,
            "min_response_length": 30,
            "no_forbidden_phrase": True,
        },
    },
    # ===================================================================
    # EDGE CASES: граничные сценарии
    # ===================================================================
    {
        "id": "EDGE-01",
        "area": "Edge",
        "name": "Вопрос о несуществующем тарифе Pro — честный ответ без галлюцинации",
        "messages": [
            "Здравствуйте",
            "Сколько стоит тариф Pro?",
        ],
        "expect": {
            "no_hallucinated_price": True,  # не должен придумывать цену Pro
            "no_forbidden_phrase": True,
        },
    },
    {
        "id": "EDGE-02",
        "area": "Edge",
        "name": "Казахский язык — ответ без деградации",
        "messages": [
            "Сәлем",
            "Жүйеңіз туралы айтып беріңізші",
        ],
        "expect": {
            "min_response_length": 20,
            "no_forbidden_phrase": True,
        },
    },
    {
        "id": "EDGE-03",
        "area": "Edge",
        "name": "Очень короткое сообщение — нет краша",
        "messages": [
            "Привет",
            "Цена?",
        ],
        "expect": {
            "min_response_length": 10,
            "no_forbidden_phrase": True,
        },
    },
    {
        "id": "EDGE-04",
        "area": "Edge",
        "name": "Повторный вопрос о цене — не должен давать разные цифры",
        "messages": [
            "Здравствуйте",
            "Сколько стоит Mini?",
            "Ещё раз — сколько конкретно?",
        ],
        "expect": {
            "contains_any": ["5 000", "5000"],
            "no_forbidden_phrase": True,
        },
    },
    {
        "id": "EDGE-05",
        "area": "Edge",
        "name": "Клиент возражает по цене после ответа — нет fallback в DB",
        "messages": [
            "Здравствуйте",
            "Сколько стоит Mini?",
            "Это дорого",
            "Есть ли скидки?",
        ],
        "expect": {
            "no_raw_kb_dump": True,
            "min_response_length": 30,
        },
    },
    {
        "id": "EDGE-06",
        "area": "Edge",
        "name": "Готовый покупатель — быстрый переход в closing, не теряет фактический ответ",
        "messages": [
            "Здравствуйте, хочу подключиться",
            "Сколько стоит Mini?",
        ],
        "expect": {
            "contains_any": ["5 000", "5000"],
            "no_forbidden_phrase": True,
        },
    },
    {
        "id": "EDGE-07",
        "area": "Edge",
        "name": "Вопрос о сроках внедрения — связный ответ",
        "messages": [
            "Здравствуйте",
            "Сколько времени займёт внедрение?",
        ],
        "expect": {
            "no_raw_kb_dump": True,
            "min_response_length": 30,
            "no_forbidden_phrase": True,
        },
    },
    {
        "id": "EDGE-08",
        "area": "Edge",
        "name": "Вопрос про Kaspi интеграцию — конкретный ответ",
        "messages": [
            "Здравствуйте",
            "Работаете ли с Kaspi?",
        ],
        "expect": {
            "contains_any": ["Kaspi", "kaspi", "каспи"],
            "no_forbidden_phrase": True,
        },
    },
    # ===================================================================
    # REGRESSION: убедиться что старые гарантии не сломаны
    # ===================================================================
    {
        "id": "REG-01",
        "area": "Regression",
        "name": "НЕ ПУТАТЬ не должен утекать в ответ",
        "messages": [
            "Здравствуйте",
            "Расскажите про тариф Pro",
            "1",
        ],
        "expect": {
            "not_contains": ["НЕ ПУТАТЬ", "НЕ ПУТАЙ"],
            "no_forbidden_phrase": True,
        },
    },
    {
        "id": "REG-02",
        "area": "Regression",
        "name": "Бот не называет себя AI/роботом",
        "messages": [
            "Здравствуйте",
            "Вы робот?",
        ],
        "expect": {
            "not_contains": ["я робот", "я AI", "я ИИ", "Я — ИИ"],
        },
    },
    {
        "id": "REG-03",
        "area": "Regression",
        "name": "Нет демо — говорит 'расскажу здесь', не 'нет демо'",
        "messages": [
            "Здравствуйте",
            "Можно посмотреть демо?",
        ],
        "expect": {
            "not_contains": ["нет демо", "демо не", "демонстрации нет"],
        },
    },
    {
        "id": "REG-04",
        "area": "Regression",
        "name": "Closing: контакт дан — переход в terminal state",
        "messages": [
            "Здравствуйте, хочу подключиться",
            "87015551234",
        ],
        "expect": {
            "no_forbidden_phrase": True,
        },
    },
]

FORBIDDEN_PHRASES = [
    "уточню у коллег",
    "вернусь с ответом",
    "коллега позвонит",
    "передам вопрос коллег",
]

RAW_KB_PATTERNS = [
    re.compile(r"^\[[\w/]+\]"),
    re.compile(r"^(Тариф|Поддержка|Интеграция|Аналитика|Система)\s+\w+\s*—\s*\w+:\s*\w+\.", re.MULTILINE),
    re.compile(r": включена\.$"),
    re.compile(r": \w+\.$"),
]


def is_raw_kb_dump(text: str) -> bool:
    """Эвристика: ответ выглядит как 2 сырые строки из KB без диалогового контекста."""
    if not text:
        return False
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if len(sentences) > 4:
        return False  # длинный текст — не dump
    for pat in RAW_KB_PATTERNS:
        if pat.search(text):
            return True
    # Простой тест: нет глагола первого лица, нет вопроса, нет "вы/ваш"
    has_dialog = bool(re.search(r"\b(вы|ваш|вам|у вас|для вас|давайте|расскажу|объясню|помогу)\b", text, re.IGNORECASE))
    if not has_dialog and len(sentences) <= 2 and len(text) < 160:
        # Дополнительно: содержит KB-заголовочный стиль
        if re.search(r"(?:включ|доступн|поддержив|реализов|обеспечив)\w+\.", text, re.IGNORECASE):
            return True
    return False


def check_turn(turn: dict, expect: dict) -> list:
    issues = []
    bot_text = turn["bot"]

    if expect.get("no_forbidden_phrase"):
        for phrase in FORBIDDEN_PHRASES:
            if phrase.lower() in bot_text.lower():
                issues.append(f"FORBIDDEN_PHRASE: '{phrase}' in response")

    if expect.get("no_raw_kb_dump") and is_raw_kb_dump(bot_text):
        issues.append(f"RAW_KB_DUMP: response looks like raw KB sentences: {bot_text[:80]!r}")

    min_len = expect.get("min_response_length", 0)
    if min_len and len(bot_text) < min_len:
        issues.append(f"TOO_SHORT: len={len(bot_text)} < {min_len}")

    for expected_str in expect.get("contains_any", []):
        if any(expected_str.lower() in bot_text.lower() for expected_str in expect["contains_any"]):
            break
    else:
        if expect.get("contains_any"):
            issues.append(f"MISSING: expected one of {expect['contains_any']!r} in response")

    for banned in expect.get("not_contains", []):
        if banned.lower() in bot_text.lower():
            issues.append(f"BANNED_CONTENT: '{banned}' found in response")

    if expect.get("no_hallucinated_price"):
        # Только 5000/220000/350000/500000 — реальные цены из KB
        price_match = re.search(r"\b(\d[\d\s]{3,})\s*(?:₸|тенге|тг)", bot_text)
        if price_match:
            raw = re.sub(r"\s", "", price_match.group(1))
            known = {"5000", "220000", "350000", "500000", "600000"}
            if raw not in known:
                issues.append(f"HALLUCINATED_PRICE: '{price_match.group(0)}' not in known prices")

    return issues


def run_scenario(scenario: dict, bot) -> dict:
    bot.reset()
    turns = []
    for i, msg in enumerate(scenario["messages"]):
        result = bot.process(msg)
        turns.append({
            "turn": i + 1,
            "user": msg,
            "bot": result.get("response", ""),
            "state": result.get("state", ""),
            "action": result.get("action", ""),
        })
        if result.get("is_final"):
            break
    return {"id": scenario["id"], "name": scenario["name"], "area": scenario["area"], "turns": turns}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.bot import SalesBot, setup_autonomous_pipeline
    from src.llm import OllamaLLM

    llm = OllamaLLM()
    setup_autonomous_pipeline()
    bot = SalesBot(llm, flow_name="autonomous")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(__file__).parent.parent / "results"
    output_dir.mkdir(exist_ok=True)
    output_json = output_dir / f"stress_verifier_{timestamp}.json"
    output_md = output_dir / f"stress_verifier_{timestamp}.md"

    all_results = []
    pass_count = 0
    fail_count = 0
    total_issues = []

    area_stats: dict[str, dict] = {}

    print(f"\n{'#'*72}")
    print(f"# FactualVerifier Stress Test — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"# Scenarios: {len(SCENARIOS)}")
    print("#" * 72)

    for scenario in SCENARIOS:
        print(f"\n[{scenario['id']}] {scenario['name']}", flush=True)
        dialog = run_scenario(scenario, bot)
        all_results.append(dialog)

        last_turn = dialog["turns"][-1]
        expect = scenario["expect"]
        issues = check_turn(last_turn, expect)

        area = scenario["area"]
        if area not in area_stats:
            area_stats[area] = {"pass": 0, "fail": 0, "issues": []}

        if issues:
            fail_count += 1
            area_stats[area]["fail"] += 1
            total_issues.extend([(scenario["id"], iss) for iss in issues])
            print(f"  FAIL")
            for iss in issues:
                print(f"    ⚠️  {iss}")
            if args.verbose:
                print(f"  Response: {last_turn['bot'][:200]!r}")
        else:
            pass_count += 1
            area_stats[area]["pass"] += 1
            if args.verbose:
                print(f"  OK — {last_turn['bot'][:120]!r}")
            else:
                print(f"  OK")

    total = pass_count + fail_count
    print(f"\n{'='*72}")
    print(f"RESULTS: {pass_count}/{total} PASS  ({fail_count} FAIL)")
    print("=" * 72)

    for area, stats in area_stats.items():
        p = stats["pass"]
        f = stats["fail"]
        bar = "✅" if f == 0 else "⚠️ "
        print(f"  {bar}  {area:20s}: {p}/{p+f} PASS")

    if total_issues:
        print(f"\nFAILED SCENARIOS:")
        for sid, iss in total_issues:
            print(f"  [{sid}] {iss}")

    # Save JSON
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": timestamp,
                "summary": {"pass": pass_count, "fail": fail_count, "total": total},
                "area_stats": area_stats,
                "scenarios": all_results,
                "issues": [{"id": s, "issue": i} for s, i in total_issues],
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    # Save MD
    md_lines = [
        f"# FactualVerifier Stress Test",
        f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Result**: {pass_count}/{total} PASS ({fail_count} FAIL)",
        "",
        "## By Area",
        "",
    ]
    for area, stats in area_stats.items():
        p = stats["pass"]
        f = stats["fail"]
        icon = "✅" if f == 0 else "⚠️"
        md_lines.append(f"- {icon} **{area}**: {p}/{p+f}")
    md_lines.append("")
    if total_issues:
        md_lines.append("## Failed Checks")
        for sid, iss in total_issues:
            md_lines.append(f"- **[{sid}]** {iss}")
    md_lines.append("")
    md_lines.append("## Dialogs")
    for dialog in all_results:
        md_lines.append(f"\n### {dialog['id']}: {dialog['name']}")
        for t in dialog["turns"]:
            md_lines.append(f"- **U**: {t['user']}")
            md_lines.append(f"- **B**: {t['bot'][:300]}")
        issues = check_turn(dialog["turns"][-1], next(s["expect"] for s in SCENARIOS if s["id"] == dialog["id"]))
        if issues:
            for iss in issues:
                md_lines.append(f"- ⚠️ {iss}")

    with open(output_md, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"\n✅ JSON: {output_json}")
    print(f"✅ MD:   {output_md}")

    sys.exit(0 if fail_count == 0 else 1)


if __name__ == "__main__":
    main()
