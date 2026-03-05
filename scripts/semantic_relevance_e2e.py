#!/usr/bin/env python3
"""
SEMANTIC RELEVANCE E2E — 10 сценариев для проверки семантической релевантности.

Целевые баги (из POST5):
  S06 T6: "Что уникального?" → пустой вопрос без содержания
  S08 T5: "AI-рекомендации?" → ответ про другую функцию (BM25 keyword overlap)
  S09 T5: "Бюджет до 300k, потянем?" → дефлексия "расскажите подробнее"

Каждый сценарий содержит probe_turns — ходы, где ожидается содержательный ответ.
Автоматический чекер + LLM-judge проверяют релевантность probe-ходов.

Использование:
  python scripts/semantic_relevance_e2e.py              # запуск
  python scripts/semantic_relevance_e2e.py --tag pre    # суффикс файла: _pre_<ts>
  python scripts/semantic_relevance_e2e.py --tag post   # суффикс файла: _post_<ts>
"""

import sys
import re
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.bot import SalesBot, setup_autonomous_pipeline
from src.llm import OllamaLLM

# ──────────────────────────────────────────────────────────────────────
# Probe checks: проверяем что ответ бота РЕЛЕВАНТЕН вопросу клиента.
# Каждый probe_turn — dict:
#   turn: int (1-based)
#   topic: str — краткое описание, что проверяем
#   must_contain_any: list[str] — ответ ДОЛЖЕН содержать хотя бы одно
#   must_not_be: list[str] — ответ НЕ должен быть таким (паттерны дефлексии)
#   check_not_off_topic: list[str] — слова, означающие ответ НЕ по теме
# ──────────────────────────────────────────────────────────────────────

DEFLECTION_PATTERNS = [
    r"расскажите\s+подробнее",
    r"расскажите\s+о\s+(своём|вашем|себе)",
    r"какой\s+у\s+вас\s+бизнес",
    r"что\s+(?:из\s+этого|именно).*(?:для\s+вас|интересует|критичн)",
    r"чем\s+(?:я\s+)?(?:могу|можем)\s+помочь",
    r"что\s+вас\s+интересует",
    r"какие?\s+задачи",
    r"давайте\s+начн[её]м\s+с",
]


def is_deflective(text: str) -> bool:
    """Проверяет, является ли ответ дефлексией (встречный вопрос без содержания)."""
    t = text.lower().strip()
    # Ответ кончается вопросом И короткий
    if t.endswith("?") and len(t) < 150:
        for pat in DEFLECTION_PATTERNS:
            if re.search(pat, t, re.IGNORECASE):
                return True
    return False


def check_relevance(
    response: str, probe: dict
) -> Tuple[bool, str]:
    """Проверяет релевантность ответа бота для probe-хода.
    Returns: (passed, reason)
    """
    low = response.lower()
    topic = probe["topic"]

    # 1. Дефлексия?
    must_not_be = probe.get("must_not_be", [])
    for pat in must_not_be:
        if re.search(pat, low, re.IGNORECASE):
            return False, f"[{topic}] Дефлексия: совпал паттерн '{pat}'"

    if is_deflective(response) and not probe.get("deflection_ok", False):
        return False, f"[{topic}] Дефлексия: пустой встречный вопрос без содержания"

    # 2. Содержит хотя бы одно ключевое слово?
    must_contain = probe.get("must_contain_any", [])
    if must_contain:
        found_any = any(kw.lower() in low for kw in must_contain)
        if not found_any:
            return False, f"[{topic}] Нет ни одного ключевого слова из {must_contain}"

    # 3. Off-topic?
    off_topic_words = probe.get("check_not_off_topic", [])
    for word in off_topic_words:
        if word.lower() in low and not any(kw.lower() in low for kw in must_contain):
            return False, f"[{topic}] Off-topic: упоминает '{word}' вместо темы вопроса"

    return True, f"[{topic}] OK"


# ══════════════════════════════════════════════════════════════════════
# 10 СЦЕНАРИЕВ
# ══════════════════════════════════════════════════════════════════════

SCENARIOS = [
    # ───────────────────────────────────────────────────
    # S01: Прямое воспроизведение S06 T6
    # "Что уникального у вас?" → бот должен перечислить преимущества
    # ───────────────────────────────────────────────────
    {
        "id": "SR01",
        "name": "S06-repro: 'Что уникального?' → содержательный ответ",
        "bug_pattern": "S06_T6: пустой вопрос без содержания",
        "msgs": [
            "Добрый день, у меня ресторан и кафе, 2 точки",
            "Сейчас на Poster, думаю сменить систему",
            "А чем вы лучше Poster? Конкретно, не общими словами",
            "А по сравнению с iiko?",
            "Ну ладно, а что уникального есть у вас, чего нет у других?",
            "Хорошо, понятно. Давайте оформим Standard",
            "87071112233",
        ],
        "probe_turns": [
            {
                "turn": 5,
                "topic": "unique_features",
                "must_contain_any": [
                    "интеграц", "функци", "аналитик", "kaspi", "маркировк",
                    "склад", "ТИС", "отчёт", "приложени", "бонус",
                    "преимущест", "уникальн", "отлича",
                ],
                "must_not_be": [
                    r"что\s+из\s+этого.*критичн",
                    r"что\s+(?:именно\s+)?(?:вас|вам)\s+интересует",
                    r"расскажите\s+подробнее",
                ],
            },
        ],
    },

    # ───────────────────────────────────────────────────
    # S02: Прямое воспроизведение S08 T5
    # "AI-рекомендации есть?" → НЕ должен говорить про "экран покупателя"
    # ───────────────────────────────────────────────────
    {
        "id": "SR02",
        "name": "S08-repro: 'AI-рекомендации?' → честный ответ, не подмена",
        "bug_pattern": "S08_T5: ответ про другую функцию (BM25 overlap)",
        "msgs": [
            "Здравствуйте, у меня строительный магазин в Алматы",
            "Нужна автоматизация — учёт, продажи",
            "А интеграция с Яндекс Маркетом есть?",
            "Ладно. А AI-рекомендации для покупателей есть? Типа как у Amazon",
            "Понятно. А что реально есть для склада?",
            "Сколько стоит Standard?",
            "Оформляйте, мой номер 87023456789",
        ],
        "probe_turns": [
            {
                "turn": 4,
                "topic": "ai_recommendations",
                "must_contain_any": [
                    "нет", "отсутств", "не предусмотрен", "пока нет",
                    "уточн", "к сожалению", "такой функции",
                    "рекомендац", "аналитик",
                ],
                "check_not_off_topic": [
                    "второй экран", "экран покупател", "экран для покупател",
                ],
            },
        ],
    },

    # ───────────────────────────────────────────────────
    # S03: Прямое воспроизведение S09 T5
    # "Бюджет до 300k, потянем?" → конкретный ответ, не "расскажите подробнее"
    # ───────────────────────────────────────────────────
    {
        "id": "SR03",
        "name": "S09-repro: 'Бюджет до 300k, потянем?' → конкретный ответ",
        "bug_pattern": "S09_T5: дефлексия вместо ответа на бюджетный вопрос",
        "msgs": [
            "Здравствуйте",
            "У меня 2 магазина косметики в Астане",
            "Сейчас всё в Excel, устали от ошибок",
            "Бюджет — до 300 тысяч в год, потянем?",
            "А что входит в Standard?",
            "Оформляйте, 87017654321",
        ],
        "probe_turns": [
            {
                "turn": 4,
                "topic": "budget_fit",
                "must_contain_any": [
                    "тариф", "тысяч", "₸", "тенге", "standard", "mini", "lite",
                    "подойд", "укладыва", "бюджет", "стоимост", "стоит",
                    "цена", "год",
                ],
                "must_not_be": [
                    r"расскажите\s+подробнее",
                    r"какой\s+у\s+вас\s+бизнес",
                    r"расскажите\s+о\s+себе",
                ],
            },
        ],
    },

    # ───────────────────────────────────────────────────
    # S04: Вариация S08 — BM25 overlap на "касса"
    # "У вас есть кассы с NFC?" → НЕ должен рассказывать про "кассовый учёт"
    # ───────────────────────────────────────────────────
    {
        "id": "SR04",
        "name": "BM25 overlap: 'кассы с NFC?' → не путать с кассовым учётом",
        "bug_pattern": "BM25 keyword overlap: 'касса' → кассовый учёт вместо оборудования",
        "msgs": [
            "Привет, у меня бутик одежды",
            "Мне нужна касса с NFC-считывателем. У вас есть такие?",
            "А терминалы какие поддерживаете?",
            "Понятно, давайте Lite оформим",
            "87475551122",
        ],
        "probe_turns": [
            {
                "turn": 2,
                "topic": "nfc_terminal",
                "must_contain_any": [
                    "оборудовани", "терминал", "NFC", "считыват",
                    "pos", "пос", "банковск", "касс", "устройств",
                    "уточн", "комплект", "модель",
                ],
                "must_not_be": [
                    r"расскажите\s+подробнее\s+о\s+(своём|вашем)",
                ],
            },
        ],
    },

    # ───────────────────────────────────────────────────
    # S05: Вариация S06 — пустой вопрос на сравнение тарифов
    # "Чем Standard отличается от Pro?" → конкретные различия
    # ───────────────────────────────────────────────────
    {
        "id": "SR05",
        "name": "Сравнение тарифов: 'Standard vs Pro?' → конкретные различия",
        "bug_pattern": "S06-вариация: пустой вопрос вместо сравнения",
        "msgs": [
            "Здравствуйте, у меня 5 точек продаж",
            "Думаю между Standard и Pro. Чем они отличаются?",
            "А по цене? Standard и Pro — конкретно сколько?",
            "Берём Pro, оформляйте",
            "87019998877",
        ],
        "probe_turns": [
            {
                "turn": 2,
                "topic": "tariff_comparison",
                "must_contain_any": [
                    "standard", "pro", "отлича", "разниц", "включа",
                    "функци", "тариф", "возможност", "точк",
                ],
                "must_not_be": [
                    r"что\s+(?:из\s+этого|именно)\s+(?:для\s+вас|вам)\s+(?:критичн|важн)",
                    r"какие?\s+задачи",
                ],
            },
            {
                "turn": 3,
                "topic": "tariff_pricing",
                "must_contain_any": [
                    "тысяч", "₸", "тенге", "цена", "стоимост", "стоит",
                    "год", "месяц",
                ],
            },
        ],
    },

    # ───────────────────────────────────────────────────
    # S06: Вариация S09 — скидка → дефлексия
    # "Дайте скидку 20%" → конкретный ответ про скидки, не "расскажите о бизнесе"
    # ───────────────────────────────────────────────────
    {
        "id": "SR06",
        "name": "Скидка: 'дайте скидку 20%' → конкретный ответ",
        "bug_pattern": "S09-вариация: дефлексия на вопрос о скидке",
        "msgs": [
            "Здравствуйте, у меня магазин продуктов, 3 точки",
            "Сколько стоит Standard на 3 точки?",
            "Дорого. Дайте скидку 20%",
            "Хотя бы 10%? Или рассрочка есть?",
            "Ладно, давайте без скидки. Оформляйте",
            "87771234567",
        ],
        "probe_turns": [
            {
                "turn": 3,
                "topic": "discount_request",
                "must_contain_any": [
                    "скидк", "акци", "рассрочк", "условия",
                    "индивидуальн", "предложени", "годов",
                    "к сожалению", "фиксирован",
                ],
                "must_not_be": [
                    r"расскажите\s+подробнее",
                    r"какой\s+у\s+вас\s+бизнес",
                ],
            },
        ],
    },

    # ───────────────────────────────────────────────────
    # S07: Вариация S08 — "CRM модуль" → не путать с ТИС
    # Wipon = ТИС, а не CRM. Если спросить про CRM → честно ответить
    # ───────────────────────────────────────────────────
    {
        "id": "SR07",
        "name": "Подмена: 'Есть CRM-модуль?' → честный ответ",
        "bug_pattern": "BM25 overlap: 'CRM' → описание ТИС вместо ответа на вопрос",
        "msgs": [
            "Добрый день, у меня розница — обувной магазин",
            "Мне нужна CRM для ведения клиентской базы. У вас есть CRM-модуль?",
            "А программа лояльности есть? Бонусные карты?",
            "Понятно, покажите что есть",
            "Давайте Mini оформим, телефон 87025559900",
        ],
        "probe_turns": [
            {
                "turn": 2,
                "topic": "crm_module",
                "must_contain_any": [
                    "CRM", "crm", "клиентск", "базу клиент", "бонус",
                    "лояльност", "учёт клиент", "карточк",
                    "нет", "отсутств", "не предусмотрен",
                    "уточн", "к сожалению",
                ],
            },
        ],
    },

    # ───────────────────────────────────────────────────
    # S08: Двойная дефлексия — 2 вопроса подряд без ответа
    # Два содержательных вопроса → бот должен ответить хотя бы на один
    # ───────────────────────────────────────────────────
    {
        "id": "SR08",
        "name": "Двойная дефлексия: 2 вопроса подряд → содержательные ответы",
        "bug_pattern": "Множественная дефлексия: бот переспрашивает вместо ответов",
        "msgs": [
            "Здравствуйте, у меня аптека в Караганде",
            "Как работает интеграция с маркировкой? Она обязательна для лекарств",
            "А ОФД подключается автоматически или вручную?",
            "Сколько стоит для одной точки?",
            "Берём, оформляйте. 87011119900",
        ],
        "probe_turns": [
            {
                "turn": 2,
                "topic": "marking_integration",
                "must_contain_any": [
                    "маркировк", "марк", "ИС МПТ", "IS MPT",
                    "модуль", "PRO УКМ", "интеграц",
                    "обязательн", "подключ",
                ],
                "must_not_be": [
                    r"расскажите\s+подробнее\s+о\s+бизнесе",
                    r"какой\s+у\s+вас\s+бизнес",
                ],
            },
            {
                "turn": 3,
                "topic": "ofd_connection",
                "must_contain_any": [
                    "ОФД", "OFD", "подключ", "автоматическ", "настро",
                    "фискал", "касс",
                ],
            },
        ],
    },

    # ───────────────────────────────────────────────────
    # S09: Ответ про ДРУГУЮ функцию (keyword overlap "оплата")
    # "Какие способы оплаты тарифа?" → бот не должен рассказывать
    # про способы приёма оплаты в магазине
    # ───────────────────────────────────────────────────
    {
        "id": "SR09",
        "name": "Overlap 'оплата': способ оплаты тарифа ≠ приём оплат в магазине",
        "bug_pattern": "BM25 overlap: 'оплата' → приём оплат вместо оплаты тарифа",
        "msgs": [
            "Здравствуйте, магазин мебели, 2 точки",
            "Мне Standard подходит по функциям",
            "Какие способы оплаты тарифа у вас? Можно с расчётного счёта?",
            "А рассрочка на тариф есть?",
            "Давайте оформим, 87473334455",
        ],
        "probe_turns": [
            {
                "turn": 3,
                "topic": "tariff_payment_method",
                "must_contain_any": [
                    "счёт", "счет", "kaspi", "каспи", "оплат",
                    "банк", "перевод", "рассрочк", "карт",
                    "безнал", "нал",
                ],
                "check_not_off_topic": [
                    "приём оплат от покупател",
                    "способы оплаты в магазине",
                ],
            },
        ],
    },

    # ───────────────────────────────────────────────────
    # S10: Контроль — корректные ответы НЕ должны блокироваться
    # Обычный discovery → presentation → closing, без дефлексий
    # probe_turns проверяют что ПРАВИЛЬНЫЕ ответы НЕ ломаются
    # ───────────────────────────────────────────────────
    {
        "id": "SR10",
        "name": "Контроль: обычный диалог — ответы не должны ломаться",
        "bug_pattern": "False positive control: проверяем что нормальные ответы не блокируются",
        "msgs": [
            "Добрый день, у нас продуктовый магазин в Шымкенте",
            "Какие тарифы есть?",
            "Что входит в Mini?",
            "А складской учёт есть?",
            "Хорошо, давайте Mini. Как подключиться?",
            "Мой телефон 87751234567",
        ],
        "probe_turns": [
            {
                "turn": 2,
                "topic": "tariffs_list",
                "must_contain_any": [
                    "тариф", "mini", "lite", "standard", "pro",
                    "план", "пакет",
                ],
                "deflection_ok": False,
            },
            {
                "turn": 3,
                "topic": "mini_contents",
                "must_contain_any": [
                    "mini", "включа", "вход", "функци", "касс",
                    "продаж", "учёт", "точк",
                ],
            },
            {
                "turn": 4,
                "topic": "warehouse",
                "must_contain_any": [
                    "склад", "учёт", "остатк", "товар", "инвентар",
                    "приёмк", "списани",
                ],
            },
        ],
    },
]

DIVIDER = "─" * 80


def run_dialog(scenario: dict, bot: SalesBot) -> dict:
    bot.reset()
    turns = []
    transitions = []
    prev_state = "greeting"
    start = time.time()

    for i, msg in enumerate(scenario["msgs"]):
        t0 = time.time()
        result = bot.process(msg)
        elapsed = time.time() - t0

        cur_state = result.get("state", "?")
        if cur_state != prev_state:
            transitions.append(f"T{i+1}: {prev_state} → {cur_state}")
            prev_state = cur_state

        turn_data = {
            "turn": i + 1,
            "user": msg,
            "bot": result["response"],
            "state": cur_state,
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

        turns.append(turn_data)
        if result.get("is_final"):
            break

    total_time = round(time.time() - start, 2)
    return {
        "id": scenario["id"],
        "name": scenario["name"],
        "bug_pattern": scenario["bug_pattern"],
        "expected_transitions": scenario.get("expected_transitions", []),
        "actual_transitions": transitions,
        "turns": turns,
        "total_time_s": total_time,
        "num_turns": len(turns),
        "final_state": turns[-1]["state"] if turns else "?",
    }


def evaluate_probes(dialog: dict, scenario: dict) -> List[dict]:
    """Проверяет probe_turns для сценария. Возвращает список результатов."""
    results = []
    probes = scenario.get("probe_turns", [])
    turns = dialog.get("turns", [])

    for probe in probes:
        target_turn = probe["turn"]
        # Найти ход в результатах
        turn_data = None
        for t in turns:
            if t["turn"] == target_turn:
                turn_data = t
                break

        if turn_data is None:
            results.append({
                "turn": target_turn,
                "topic": probe["topic"],
                "passed": False,
                "reason": f"Ход {target_turn} не найден (диалог завершился раньше)",
                "bot_response": "",
            })
            continue

        passed, reason = check_relevance(turn_data["bot"], probe)
        results.append({
            "turn": target_turn,
            "topic": probe["topic"],
            "passed": passed,
            "reason": reason,
            "bot_response": turn_data["bot"][:200],
            "intent": turn_data.get("intent", "?"),
            "action": turn_data.get("action", "?"),
        })

    return results


def format_dialog(d: dict, probe_results: List[dict]) -> str:
    lines = [
        f"\n{'='*80}",
        f"  {d['id']} | {d['name']}",
        f"  Bug: {d['bug_pattern']}",
        f"  Ходов: {d['num_turns']} | Время: {d['total_time_s']}s | Финал: {d['final_state']}",
        f"{'='*80}",
        "",
    ]

    # Probe results
    if probe_results:
        lines.append("  PROBE RESULTS:")
        for pr in probe_results:
            mark = "PASS" if pr["passed"] else "FAIL"
            icon = "✅" if pr["passed"] else "❌"
            lines.append(f"    {icon} T{pr['turn']} [{mark}] {pr['reason']}")
            if not pr["passed"]:
                lines.append(f"       Ответ бота: {pr['bot_response']}")
        lines.append("")

    lines.append("  ПЕРЕХОДЫ:")
    for at in d["actual_transitions"]:
        lines.append(f"    🔄 {at}")
    if not d["actual_transitions"]:
        lines.append("    (нет)")
    lines.append("")

    for t in d["turns"]:
        lines.append(DIVIDER)
        # Отметить probe-ходы
        is_probe = any(pr["turn"] == t["turn"] for pr in probe_results)
        probe_mark = " 🎯" if is_probe else ""
        meta = (
            f"T{t['turn']}{probe_mark} | state={t['state']} | intent={t['intent']} "
            f"| action={t['action']} | spin={t['spin_phase']} | {t['elapsed_s']}s"
        )
        lines.append(f"  [{meta}]")
        lines.append(f"  К: {t['user']}")
        lines.append(f"  Б: {t['bot']}")
        if t.get("extracted_data"):
            lines.append(f"  📋 {t['extracted_data']}")
        if t["is_final"]:
            lines.append("  ✅ ФИНАЛ")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Semantic Relevance E2E Test")
    parser.add_argument("--tag", type=str, default="",
                        help="Tag для имени файла (pre/post)")
    args = parser.parse_args()

    setup_autonomous_pipeline()

    llm = OllamaLLM()
    bot = SalesBot(llm, flow_name="autonomous")

    all_results = []
    all_probes = []
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = f"_{args.tag}" if args.tag else ""
    json_path = Path(__file__).parent.parent / "results" / f"semantic_relevance{tag}_{ts}.json"
    md_path = Path(__file__).parent.parent / "results" / f"semantic_relevance{tag}_{ts}.md"
    json_path.parent.mkdir(exist_ok=True)

    print(f"\n{'='*80}")
    print(f"  SEMANTIC RELEVANCE E2E — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if args.tag:
        print(f"  Tag: {args.tag}")
    print(f"{'='*80}")

    total_probes = 0
    passed_probes = 0

    for scenario in SCENARIOS:
        print(f"\n>>> [{scenario['id']}] {scenario['name']} ({len(scenario['msgs'])} ходов)...")
        dialog = run_dialog(scenario, bot)
        probe_results = evaluate_probes(dialog, scenario)
        formatted = format_dialog(dialog, probe_results)
        print(formatted)

        # Считаем статистику
        for pr in probe_results:
            total_probes += 1
            if pr["passed"]:
                passed_probes += 1

        dialog["probe_results"] = probe_results
        all_results.append(dialog)
        all_probes.extend(probe_results)

    # --- Сводка ---
    print(f"\n{'='*80}")
    print("  СВОДКА PROBE CHECKS")
    print(f"{'='*80}\n")

    for d in all_results:
        probes = d.get("probe_results", [])
        all_pass = all(p["passed"] for p in probes) if probes else True
        icon = "✅" if all_pass else "❌"
        print(f"  {icon} {d['id']} | {d['name']}")
        for pr in probes:
            mark = "PASS" if pr["passed"] else "FAIL"
            pi = "  ✅" if pr["passed"] else "  ❌"
            print(f"    {pi} T{pr['turn']} [{mark}] {pr['reason']}")
        print()

    print(f"\n  ИТОГО: {passed_probes}/{total_probes} probes passed "
          f"({100*passed_probes/total_probes:.0f}%)" if total_probes > 0 else "")

    # --- Сохранение ---
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": ts,
            "tag": args.tag,
            "total_probes": total_probes,
            "passed_probes": passed_probes,
            "pass_rate": round(passed_probes / total_probes * 100, 1) if total_probes else 0,
            "scenarios": all_results,
        }, f, ensure_ascii=False, indent=2)

    # Markdown report
    md_lines = [
        f"# Semantic Relevance E2E — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Tag:** {args.tag or '(none)'}",
        "",
        "## Сводка",
        "",
        f"**Probes:** {passed_probes}/{total_probes} "
        f"({100*passed_probes/total_probes:.0f}%)" if total_probes else "",
        "",
        "| ID | Сценарий | Bug Pattern | Probes | Результат |",
        "|----|----------|-------------|--------|-----------|",
    ]
    for d in all_results:
        probes = d.get("probe_results", [])
        n_pass = sum(1 for p in probes if p["passed"])
        n_total = len(probes)
        all_pass = n_pass == n_total
        icon = "PASS" if all_pass else "FAIL"
        md_lines.append(
            f"| {d['id']} | {d['name']} | {d['bug_pattern'][:40]} | "
            f"{n_pass}/{n_total} | {icon} |"
        )

    md_lines.extend(["", "## Probe Details", ""])
    for d in all_results:
        probes = d.get("probe_results", [])
        for pr in probes:
            mark = "PASS" if pr["passed"] else "**FAIL**"
            md_lines.append(f"- `{d['id']}` T{pr['turn']} [{mark}]: {pr['reason']}")
            if not pr["passed"]:
                md_lines.append(f"  - Bot: _{pr['bot_response']}_")

    md_lines.extend(["", "## Диалоги", ""])
    for d in all_results:
        probes = d.get("probe_results", [])
        md_lines.append(format_dialog(d, probes))

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"\n  JSON: {json_path}")
    print(f"  MD:   {md_path}")


if __name__ == "__main__":
    main()
