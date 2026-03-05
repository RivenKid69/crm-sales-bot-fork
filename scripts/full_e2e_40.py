"""
Full E2E Test — 40 scenarios: LLM Judge + Factual Verifier + KB Grounding + Boundary Validator.

Tests the COMPLETE autonomous pipeline end-to-end:
  A01-A08: Pricing accuracy (prices grounded to KB)
  B01-B08: Feature grounding (only real features)
  C01-C08: Hallucination prevention (non-existent things)
  D01-D08: Multi-turn dialog quality (full SPIN flow)
  E01-E08: Edge cases (tricky inputs for verifier/judge)

Principle: KB facts are authoritative. When KB contradicts bot rules, KB wins.

Usage:
    python -m scripts.full_e2e_40 2>/dev/null
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# 40 scenarios
# ---------------------------------------------------------------------------

SCENARIOS = [

    # ======================================================================
    # GROUP A: PRICING ACCURACY (A01-A08)
    # Factual verifier + KB grounding: exact prices from KB
    # ======================================================================

    {
        "id": "A01",
        "name": "Mini: 5 000 ₸/мес — точная цена",
        "group": "pricing_accuracy",
        "checks": {
            "must_contain_any": ["5 000", "5000"],
            "must_not_contain": [
                "уточню", "не знаю", "50 000", "15 000",
                "в год",  # Mini is monthly, not yearly
            ],
        },
        "messages": [
            "Здравствуйте",
            "У меня один маленький магазин",
            "Сколько стоит тариф Mini?",
        ],
    },
    {
        "id": "A02",
        "name": "Lite: 150 000 ₸/год — точная цена",
        "group": "pricing_accuracy",
        "checks": {
            "must_contain_any": ["150 000", "150000"],
            "must_not_contain": ["уточню", "не знаю", "15 000 ₸/мес"],
        },
        "messages": [
            "Здравствуйте",
            "Один магазин косметики",
            "Сколько стоит Lite в год?",
        ],
    },
    {
        "id": "A03",
        "name": "Standard: 220 000 ₸/год — точная цена",
        "group": "pricing_accuracy",
        "checks": {
            "must_contain_any": ["220 000", "220000"],
            "must_not_contain": ["уточню", "не знаю", "200 000"],
        },
        "messages": [
            "Здравствуйте",
            "Сеть из 3 магазинов",
            "Цена Standard?",
        ],
    },
    {
        "id": "A04",
        "name": "Pro: 500 000 ₸/год — точная цена",
        "group": "pricing_accuracy",
        "checks": {
            "must_contain_any": ["500 000", "500000"],
            "must_not_contain": ["уточню", "не знаю", "50 000"],
        },
        "messages": [
            "Здравствуйте",
            "Крупная сеть 15 точек, нужен максимальный тариф",
            "Сколько стоит Pro?",
        ],
    },
    {
        "id": "A05",
        "name": "Моноблок POS i3: 140 000 ₸ — оборудование из KB",
        "group": "pricing_accuracy",
        "checks": {
            "must_contain_any": ["140 000", "140000"],
            "must_not_contain": ["уточню", "не знаю цену"],
        },
        "messages": [
            "Здравствуйте",
            "Один магазин продуктов",
            "Сколько стоит самый простой кассовый моноблок?",
        ],
    },
    {
        "id": "A06",
        "name": "Бот НЕ считает за клиента (5×Mini ≠ 25000)",
        "group": "pricing_accuracy",
        "checks": {
            "must_not_contain": ["25 000", "25000"],
            "must_contain_any": ["5 000", "Mini"],
        },
        "messages": [
            "Здравствуйте",
            "5 маленьких точек",
            "Если взять Mini на каждую, сколько суммарно в месяц?",
        ],
    },
    {
        "id": "A07",
        "name": "Рассрочка Kaspi 0-0-12 — факт из KB",
        "group": "pricing_accuracy",
        "checks": {
            "must_contain_any": ["рассрочк", "Kaspi", "kaspi", "0-0-12", "12 месяц"],
            "must_not_contain": ["рассрочка недоступна", "не знаю"],
        },
        "messages": [
            "Здравствуйте",
            "Есть ли рассрочка на оборудование?",
        ],
    },
    {
        "id": "A08",
        "name": "ТИС: 220 000 ₸/год за 1 точку — отдельный продукт",
        "group": "pricing_accuracy",
        "checks": {
            "must_contain_any": ["220 000", "ТИС", "тис"],
            "must_not_contain": ["уточню цену", "не знаю"],
        },
        "messages": [
            "Здравствуйте",
            "Нужна ТИС для ИП, 1 точка",
            "Сколько стоит ТИС?",
        ],
    },

    # ======================================================================
    # GROUP B: FEATURE GROUNDING (B01-B08)
    # Bot claims ONLY features that exist in KB
    # ======================================================================

    {
        "id": "B01",
        "name": "Kaspi интеграция: Lite/Standard/Pro — да, Mini — нет",
        "group": "feature_grounding",
        "checks": {
            "must_not_contain": [
                "mini поддерживает kaspi", "mini интегрируется",
                "любой тариф поддерживает kaspi", "все тарифы",
            ],
        },
        "messages": [
            "Здравствуйте",
            "Нам важна интеграция с Kaspi",
            "Mini поддерживает Kaspi?",
        ],
    },
    {
        "id": "B02",
        "name": "1С интеграция — есть (в KB)",
        "group": "feature_grounding",
        "checks": {
            "must_contain_any": ["1С", "1с", "1C"],
            "must_not_contain": ["нет интеграции с 1с", "не поддерживаем 1с"],
        },
        "messages": [
            "Здравствуйте",
            "У нас учёт в 1С",
            "Wipon работает с 1С?",
        ],
    },
    {
        "id": "B03",
        "name": "Wipon Pro УКМ: маркировка, алкоголь — 12 000 ₸/год",
        "group": "feature_grounding",
        "checks": {
            "must_contain_any": ["маркировк", "алкогол", "акциз", "УКМ", "укм", "Pro"],
            "must_not_contain": ["нет поддержки маркировки"],
        },
        "messages": [
            "Здравствуйте",
            "Магазин алкоголя",
            "Есть ли у вас поддержка маркировки для акцизной продукции?",
        ],
    },
    {
        "id": "B04",
        "name": "Складской учёт — есть в Standard+",
        "group": "feature_grounding",
        "checks": {
            "must_contain_any": ["склад", "остат", "номенклатур", "учёт", "учет"],
            "must_not_contain": ["нет складского учёта", "уточню"],
        },
        "messages": [
            "Здравствуйте",
            "Продуктовый магазин, 2 точки",
            "Есть ли складской учёт? Нужно контролировать остатки",
        ],
    },
    {
        "id": "B05",
        "name": "Аналитика продаж — есть в Pro",
        "group": "feature_grounding",
        "checks": {
            "must_contain_any": ["аналитик", "отчёт", "отчет", "ABC", "abc", "продаж"],
            "must_not_contain": ["нет аналитики"],
        },
        "messages": [
            "Здравствуйте",
            "Большая сеть магазинов",
            "Какая аналитика продаж доступна?",
        ],
    },
    {
        "id": "B06",
        "name": "Кадровый учёт — только Pro",
        "group": "feature_grounding",
        "checks": {
            "must_contain_any": ["кадр", "сотрудник", "персонал", "Pro", "про"],
            "must_not_contain": ["нет кадрового учёта", "не поддерживаем"],
        },
        "messages": [
            "Здравствуйте",
            "Сеть из 10 магазинов, много сотрудников",
            "Есть ли кадровый учёт?",
        ],
    },
    {
        "id": "B07",
        "name": "ОФД — включён во все тарифы",
        "group": "feature_grounding",
        "checks": {
            "must_contain_any": ["ОФД", "офд", "фискал"],
            "must_not_contain": ["офд не включён", "офд платный", "нет офд"],
        },
        "messages": [
            "Здравствуйте",
            "ОФД входит в стоимость или отдельно платить?",
        ],
    },
    {
        "id": "B08",
        "name": "Cashback модуль — только в Pro",
        "group": "feature_grounding",
        "checks": {
            "must_contain_any": ["cashback", "Cashback", "кэшбэк", "кешбек", "бонус", "скидк", "Pro", "про"],
        },
        "messages": [
            "Здравствуйте",
            "Хотим начислять клиентам кешбек с покупок",
            "Есть ли у вас система кешбека?",
        ],
    },

    # ======================================================================
    # GROUP C: HALLUCINATION PREVENTION (C01-C08)
    # Things that DO NOT exist — bot must NOT claim them
    # ======================================================================

    {
        "id": "C01",
        "name": "Пробный период — ответ из БД: 7 дней, бесплатно",
        "group": "hallucination_prevention",
        "checks": {
            # KB says: 7 days trial, 0₸. Bot must give correct KB data.
            "must_contain_any": ["7", "бесплатн", "пробн", "тест"],
            "must_not_contain": [
                "14 дней", "30 дней", "месяц бесплатно",  # wrong durations
                "99 ₸", "1000 ₸",  # wrong prices
            ],
        },
        "messages": [
            "Здравствуйте",
            "Магазин одежды в Астане",
            "Есть ли пробный период чтобы протестировать?",
        ],
    },
    {
        "id": "C02",
        "name": "CRM модуль — НЕТ",
        "group": "hallucination_prevention",
        "checks": {
            "must_not_contain": [
                "crm-модуль", "crm модуль", "встроенная crm",
                "воронка продаж", "да, crm",
            ],
        },
        "messages": [
            "Здравствуйте",
            "Нам нужна CRM для ведения клиентской базы",
            "Есть ли CRM-модуль в Wipon?",
        ],
    },
    {
        "id": "C03",
        "name": "Wolt интеграция — НЕТ",
        "group": "hallucination_prevention",
        "checks": {
            "must_not_contain": [
                "интеграция с wolt", "интегрируется с wolt",
                "подключение к wolt", "работает с wolt",
            ],
        },
        "messages": [
            "Здравствуйте",
            "Доставляем еду через Wolt",
            "Можно подключить Wipon к Wolt?",
        ],
    },
    {
        "id": "C04",
        "name": "SAP интеграция — НЕТ",
        "group": "hallucination_prevention",
        "checks": {
            "must_not_contain": [
                "интеграция с sap", "работает с sap", "поддерживаем sap",
                "подключение к sap",
            ],
        },
        "messages": [
            "Здравствуйте",
            "Наш головной офис использует SAP",
            "Wipon может интегрироваться с SAP?",
        ],
    },
    {
        "id": "C05",
        "name": "Мобильное приложение для покупателей — НЕТ",
        "group": "hallucination_prevention",
        "checks": {
            "must_not_contain": [
                "мобильное приложение для покупателей",
                "приложение для клиентов",
                "приложение для заказов",
            ],
        },
        "messages": [
            "Здравствуйте",
            "Хотим чтобы клиенты заказывали через приложение",
            "Есть ли мобильное приложение для покупателей?",
        ],
    },
    {
        "id": "C06",
        "name": "Аренда оборудования — НЕТ (бот отказывает)",
        "group": "hallucination_prevention",
        "checks": {
            # Bot may SAY "в аренду" but only in denial context
            # Real hallucination = "можно арендовать", "аренда доступна"
            "must_not_contain": [
                "можно арендовать", "аренда доступна", "предоставляем в аренду",
                "арендуйте", "можно взять в аренду",
            ],
        },
        "messages": [
            "Здравствуйте",
            "Не хочу покупать оборудование сразу",
            "Можно взять кассу в аренду?",
        ],
    },
    {
        "id": "C07",
        "name": "SLA 99.9% — НЕТ (не раскрываем)",
        "group": "hallucination_prevention",
        "checks": {
            "must_not_contain": [
                "99.9%", "99,9%", "гарантируем доступность 99",
                "uptime 99",
            ],
        },
        "messages": [
            "Здравствуйте",
            "Для нас критична надёжность системы",
            "Какой у вас SLA? Гарантируете ли 99.9% аптайм?",
        ],
    },
    {
        "id": "C08",
        "name": "Bitrix24 интеграция — НЕТ",
        "group": "hallucination_prevention",
        "checks": {
            "must_not_contain": [
                "интегрируется с bitrix", "интеграция с bitrix",
                "работает с bitrix", "подключение к bitrix",
            ],
        },
        "messages": [
            "Здравствуйте",
            "Используем Bitrix24 для учёта",
            "Wipon интегрируется с Bitrix24?",
        ],
    },

    # ======================================================================
    # GROUP D: MULTI-TURN DIALOG QUALITY (D01-D08)
    # Full autonomous SPIN flow, all components together
    # ======================================================================

    {
        "id": "D01",
        "name": "Discovery → цена: бот отвечает фактами из KB",
        "group": "multi_turn_quality",
        "checks": {
            "must_contain_any": ["₸", "тенге", "тариф"],
            "must_not_contain": [
                "уточню цену", "не могу назвать",
                "расскажите о компании",  # бизнес-тип уже известен
            ],
        },
        "messages": [
            "Здравствуйте",
            "Продуктовый магазин, 1 точка, Алматы",
            "Интересуют цены на вашу систему",
        ],
    },
    {
        "id": "D02",
        "name": "Возражение 'дорого' → конкурентное сравнение из KB",
        "group": "multi_turn_quality",
        "checks": {
            "must_not_contain": [
                "менеджер свяжется", "наш менеджер",
                "99.9%", "uptime",
            ],
        },
        "messages": [
            "Здравствуйте",
            "Ресторан, 2 точки",
            "Сколько стоит Standard?",
            "Дорого. Poster дешевле вроде",
        ],
    },
    {
        "id": "D03",
        "name": "Ready buyer → быстрый путь к closing + сбор контакта",
        "group": "multi_turn_quality",
        "checks": {
            "must_not_contain": [
                "менеджер свяжется",
            ],
        },
        "messages": [
            "Здравствуйте",
            "Мне нужна касса для магазина, одна точка",
            "Хочу подключиться, давайте оформим",
            "Мой номер 87077654321",
        ],
    },
    {
        "id": "D04",
        "name": "Казахоязычный клиент — бот отвечает на казахском",
        "group": "multi_turn_quality",
        "checks": {
            # Bot should NOT respond in pure Russian to Kazakh messages
            "must_not_contain": [
                "расскажите о вашем бизнесе",  # Russian SPIN question to Kazakh speaker
            ],
        },
        "messages": [
            "Сәлеметсіз бе",
            "Менің шағын дүкенім бар, Алматыда",
            "Бағасы қанша?",
        ],
    },
    {
        "id": "D05",
        "name": "Переговоры: бот не придумывает скидки",
        "group": "multi_turn_quality",
        "checks": {
            "must_not_contain": [
                "скидка 50%", "скидка 30%", "скидка 20%",
                "дадим скидку", "персональная скидка",
                "специальная цена только для вас",
            ],
        },
        "messages": [
            "Здравствуйте",
            "Сеть 5 магазинов одежды",
            "Сколько стоит Standard?",
            "Дорого, дайте скидку",
        ],
    },
    {
        "id": "D06",
        "name": "Технический deep-dive: оборудование из KB",
        "group": "multi_turn_quality",
        "checks": {
            "must_contain_any": [
                "сканер", "принтер", "POS", "моноблок", "pos",
                "весы", "ТСД", "тсд",
            ],
            "must_not_contain": ["уточню у коллег"],
        },
        "messages": [
            "Здравствуйте",
            "Продуктовый магазин с весовым товаром",
            "Какое оборудование мне нужно? Сканер, весы, принтер?",
        ],
    },
    {
        "id": "D07",
        "name": "Длинный диалог 8 ходов — нет повторов вопросов",
        "group": "multi_turn_quality",
        "checks": {
            "must_not_contain": [
                # Бот не должен переспрашивать бизнес-тип после хода 2
                "какой у вас бизнес",
                "расскажите о вашем бизнесе",
                "чем занимаетесь",
            ],
        },
        "messages": [
            "Здравствуйте",
            "Аптека, 3 точки в Алматы",
            "Главная проблема — расхождения остатков",
            "Какой тариф подойдёт?",
            "А Kaspi QR работает?",
            "Что по оборудованию?",
            "Есть рассрочка?",
            "Хорошо, хочу подключиться",
        ],
    },
    {
        "id": "D08",
        "name": "Клиент меняет тему: цена → поддержка → closing",
        "group": "multi_turn_quality",
        "checks": {
            "must_not_contain": [
                "менеджер свяжется",
            ],
        },
        "messages": [
            "Здравствуйте",
            "Кафе в Шымкенте",
            "Какие тарифы есть?",
            "А поддержка как работает? Быстро отвечаете?",
            "Ок, давайте подключим Standard",
        ],
    },

    # ======================================================================
    # GROUP E: EDGE CASES (E01-E08)
    # Tricky inputs that test verifier/judge limits
    # ======================================================================

    {
        "id": "E01",
        "name": "Омоним 'стоит': 'не стоит тратить время' → objection handling, не полный прайс",
        "group": "edge_cases",
        "checks": {
            # User says "не стоит тратить время на дорогие системы" — this is an OBJECTION,
            # not a price question. Bot may mention a starting price as objection handling
            # (that's good sales), but should NOT dump a full tariff breakdown.
            "must_not_contain": [
                "150 000", "220 000", "500 000",  # full tariff list = over-response
            ],
        },
        "messages": [
            "Здравствуйте",
            "Магазин обуви, 1 точка",
            "Не стоит тратить время на дорогие системы",
        ],
    },
    {
        "id": "E02",
        "name": "Клиент называет неправильную цену — бот поправляет из KB",
        "group": "edge_cases",
        "checks": {
            "must_contain_any": ["150 000", "150000"],
            "must_not_contain": ["100 000", "100000"],
        },
        "messages": [
            "Здравствуйте",
            "Один магазин",
            "Мне сказали что Lite стоит 100 000 в год, это правда?",
        ],
    },
    {
        "id": "E03",
        "name": "Сравнение с конкурентом — честные факты из KB",
        "group": "edge_cases",
        "checks": {
            "must_not_contain": [
                "наши клиенты из", "компания", "«",  # no fabricated testimonials
            ],
        },
        "messages": [
            "Здравствуйте",
            "Сейчас используем Poster",
            "Чем вы лучше Poster?",
        ],
    },
    {
        "id": "E04",
        "name": "Смешанный язык: рус+каз — бот не ломается",
        "group": "edge_cases",
        "checks": {
            "must_not_contain": ["error", "traceback", "ошибка"],
        },
        "messages": [
            "Сәлем, здравствуйте",
            "Менің дүкенім бар, продукты продаю",
            "Бағасы қанша ваших тарифов?",
        ],
    },
    {
        "id": "E05",
        "name": "Расплывчатый вопрос → бот использует контекст из KB",
        "group": "edge_cases",
        "checks": {
            "must_not_contain": [
                "не понимаю", "переформулируйте",
                "error", "traceback",
            ],
        },
        "messages": [
            "Здравствуйте",
            "Магазин электроники",
            "Ну и что вы можете предложить?",
        ],
    },
    {
        "id": "E06",
        "name": "Два вопроса в одном сообщении: цена + пробный период",
        "group": "edge_cases",
        "checks": {
            # Bot should address BOTH questions: pricing + trial (both in KB)
            "must_contain_any": ["₸", "тенге", "тариф", "5 000", "150 000"],
            "must_not_contain": ["14 дней", "30 дней"],  # wrong trial duration
        },
        "messages": [
            "Здравствуйте",
            "Магазин продуктов, 1 точка",
            "Сколько стоит и есть ли пробный период?",
        ],
    },
    {
        "id": "E07",
        "name": "Follow-up после цены: уточнение не сбрасывает контекст",
        "group": "edge_cases",
        "checks": {
            "must_not_contain": [
                "какой у вас бизнес", "расскажите о компании",
            ],
        },
        "messages": [
            "Здравствуйте",
            "Кондитерская, 1 точка",
            "Сколько стоит Lite?",
            "А что в него входит?",
            "А оборудование отдельно?",
        ],
    },
    {
        "id": "E08",
        "name": "Клиент говорит 14 дней — бот поправляет на 7 (из БД)",
        "group": "edge_cases",
        "checks": {
            # KB says 7 days. Client says 14. Bot must correct.
            "must_contain_any": ["7"],
            "must_not_contain": [
                "14 дней", "да, 14", "верно, 14",
            ],
        },
        "messages": [
            "Здравствуйте",
            "Магазин одежды",
            "Мне сказали что у вас тестовый период 14 дней, верно?",
        ],
    },
]


# ---------------------------------------------------------------------------
# Check runner (combines pattern checks from bug4 + trial/cap from verifier)
# ---------------------------------------------------------------------------

def _run_checks(scenario: dict, turns: list) -> list:
    """Run all checks for a scenario and return list of issues."""
    issues = []
    checks = scenario.get("checks", {})
    all_bot = " ".join(t["bot"] for t in turns)
    all_bot_lower = all_bot.lower()

    # --- must_contain_any ---
    must_any = checks.get("must_contain_any", [])
    if must_any and not any(p.lower() in all_bot_lower for p in must_any):
        issues.append(
            f"FAIL must_contain_any: none of {must_any} found in bot responses"
        )

    # --- must_not_contain ---
    for phrase in checks.get("must_not_contain", []):
        if phrase.lower() in all_bot_lower:
            for t in turns:
                if phrase.lower() in t["bot"].lower():
                    preview = t["bot"][:200]
                    issues.append(
                        f"FAIL must_not_contain: '{phrase}' at turn {t['turn']}: "
                        f"«{preview}»"
                    )
                    break

    # --- must_contain_all (all phrases must appear) ---
    for phrase in checks.get("must_contain_all", []):
        if phrase.lower() not in all_bot_lower:
            issues.append(f"FAIL must_contain_all: '{phrase}' not found")

    # --- price_grounding: check that any mentioned price is in retrieved_facts ---
    if checks.get("price_grounding"):
        _check_price_grounding(turns, issues)

    return issues


def _check_price_grounding(turns: list, issues: list):
    """Verify that prices mentioned by bot exist in retrieved_facts."""
    price_re = re.compile(r'(\d[\d\s]*\d)\s*₸')
    for t in turns:
        facts = t.get("retrieved_facts", "")
        if not facts:
            continue
        for m in price_re.finditer(t["bot"]):
            raw_price = m.group(1).replace(" ", "")
            # Check if this price is grounded in facts
            if raw_price not in facts.replace(" ", ""):
                issues.append(
                    f"PRICE UNGROUNDED at turn {t['turn']}: "
                    f"{m.group(0)} not in retrieved_facts"
                )


# ---------------------------------------------------------------------------
# Dialog runner
# ---------------------------------------------------------------------------

def run_dialog(scenario: dict, bot) -> dict:
    bot.reset()
    turns = []
    for i, msg in enumerate(scenario["messages"]):
        result = bot.process(msg)
        turn_data = {
            "turn": i + 1,
            "user": msg,
            "bot": result["response"],
            "state": result.get("state", ""),
            "action": result.get("action", ""),
            "spin_phase": result.get("spin_phase", ""),
            "template": result.get("template_key", ""),
        }
        # Capture verifier metadata if available
        meta = result.get("_factual_verifier_meta") or result.get("metadata", {})
        if meta:
            turn_data["verifier_meta"] = {
                k: v for k, v in meta.items()
                if k.startswith("factual_verifier")
            }
        turns.append(turn_data)
        if result.get("is_final"):
            break

    issues = _run_checks(scenario, turns)
    return {
        "id": scenario["id"],
        "name": scenario["name"],
        "group": scenario["group"],
        "turns": turns,
        "issues": issues,
        "passed": len(issues) == 0,
    }


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def build_report(dialogs: list) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"# Full E2E 40 Scenarios Report — {ts}\n"]

    # Overall
    total_pass = sum(d["passed"] for d in dialogs)
    lines.append(f"## Overall: {total_pass}/{len(dialogs)} PASS\n")

    # Per-group summary
    groups: dict = {}
    for d in dialogs:
        g = d["group"]
        groups.setdefault(g, {"pass": 0, "fail": 0})
        if d["passed"]:
            groups[g]["pass"] += 1
        else:
            groups[g]["fail"] += 1

    lines.append("| Group | PASS | FAIL | Total |")
    lines.append("|-------|------|------|-------|")
    for group, c in groups.items():
        total = c["pass"] + c["fail"]
        lines.append(f"| {group} | {c['pass']} | {c['fail']} | {total} |")
    lines.append("")

    # Failed scenarios summary
    failed = [d for d in dialogs if not d["passed"]]
    if failed:
        lines.append("## Failed Scenarios\n")
        for d in failed:
            lines.append(f"- **{d['id']}** [{d['group']}]: {d['name']}")
            for issue in d["issues"]:
                lines.append(f"  - {issue}")
        lines.append("")

    # Detailed results
    lines.append("## Detailed Results\n")
    for d in dialogs:
        status = "✅ PASS" if d["passed"] else "❌ FAIL"
        lines.append(f"---\n### {d['id']} {status} [{d['group']}] — {d['name']}")

        for t in d["turns"]:
            lines.append(f"**U{t['turn']}:** {t['user']}")
            preview = t["bot"][:500] + ("…" if len(t["bot"]) > 500 else "")
            lines.append(f"**B{t['turn']}:** {preview}")
            lines.append(
                f"  `[{t['state']}] action={t['action']} "
                f"spin={t['spin_phase']} tpl={t['template']}`"
            )
            # Verifier metadata
            vm = t.get("verifier_meta")
            if vm:
                lines.append(f"  `verifier: {vm}`")
            lines.append("")

        if d["issues"]:
            lines.append("**Issues:**")
            for issue in d["issues"]:
                lines.append(f"- {issue}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.bot import SalesBot, setup_autonomous_pipeline
    from src.llm import OllamaLLM

    setup_autonomous_pipeline()

    llm = OllamaLLM()
    bot = SalesBot(llm, flow_name="autonomous")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = Path(__file__).parent.parent / "results"
    results_dir.mkdir(exist_ok=True)
    json_path = results_dir / f"full_e2e_40_{ts}.json"
    md_path = results_dir / f"full_e2e_40_{ts}.md"

    all_dialogs = []
    group_stats: dict = {}

    print(f"\n{'='*70}")
    print(f"Full E2E 40 Scenarios — {ts}")
    print(f"Flags: verifier=ON  boundary=ON  llm_judge=ON  retry=ON  fallback=ON")
    print(f"{'='*70}\n")

    for scenario in SCENARIOS:
        sid = scenario["id"]
        sname = scenario["name"]
        sgroup = scenario["group"]

        print(f"  {sid} [{sgroup}] {sname} ...", end="", flush=True)
        dialog = run_dialog(scenario, bot)
        all_dialogs.append(dialog)

        group_stats.setdefault(sgroup, {"pass": 0, "fail": 0})
        if dialog["passed"]:
            group_stats[sgroup]["pass"] += 1
            print(f"  PASS", flush=True)
        else:
            group_stats[sgroup]["fail"] += 1
            print(f"  FAIL", flush=True)
            for issue in dialog["issues"]:
                print(f"       {issue[:120]}", flush=True)

    # Save results
    report = build_report(all_dialogs)
    md_path.write_text(report, encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {"timestamp": ts, "scenarios_count": len(SCENARIOS), "dialogs": all_dialogs},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # Summary
    total_pass = sum(d["passed"] for d in all_dialogs)
    print(f"\n{'='*70}")
    print(f"RESULT: {total_pass}/{len(all_dialogs)} PASS")
    print()
    for group, c in group_stats.items():
        total = c["pass"] + c["fail"]
        print(f"  {group}: {c['pass']}/{total}")
    print(f"\nReport: {md_path}")
    print(f"JSON:   {json_path}")
    print(f"{'='*70}")

    # Exit code for CI
    sys.exit(0 if total_pass == len(all_dialogs) else 1)


if __name__ == "__main__":
    main()
