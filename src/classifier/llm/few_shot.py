"""Few-shot примеры для LLM классификатора с alternatives.

Каждый пример содержит:
  - message: сообщение клиента
  - context: контекст диалога (state, spin_phase, last_action)
  - result: ожидаемый результат классификации
  - priority: 1=anchor (всегда), 2=high-value, 3=conditional
  - require_context: условия для context-aware отбора (опционально)
"""

FEW_SHOT_EXAMPLES = [
    # ─────────────────────────────────────────────
    # idx 0: Приветствия — anchor
    # ─────────────────────────────────────────────
    {
        "message": "Привет!",
        "context": {},
        "result": {
            "intent": "greeting",
            "confidence": 0.98,
            "reasoning": "Стандартное приветствие",
            "alternatives": [
                {"intent": "small_talk", "confidence": 0.15},
                {"intent": "agreement", "confidence": 0.10}
            ]
        },
        "priority": 1,
        "require_context": {},
    },

    # ─────────────────────────────────────────────
    # idx 1: Ценовые — anchor
    # ─────────────────────────────────────────────
    {
        "message": "Сколько стоит ваша система?",
        "context": {},
        "result": {
            "intent": "price_question",
            "confidence": 0.97,
            "reasoning": "Прямой вопрос о цене",
            "alternatives": [
                {"intent": "pricing_details", "confidence": 0.25},
                {"intent": "question_features", "confidence": 0.10}
            ]
        },
        "priority": 1,
        "require_context": {},
    },

    # ─────────────────────────────────────────────
    # idx 2: SPIN ситуация — anchor
    # ─────────────────────────────────────────────
    {
        "message": "У нас небольшой ресторан, работает 15 человек",
        "context": {"spin_phase": "situation"},
        "result": {
            "intent": "situation_provided",
            "confidence": 0.96,
            "reasoning": "Клиент описывает свою ситуацию",
            "extracted_data": {
                "company_size": 15,
                "business_type": "ресторан"
            },
            "alternatives": [
                {"intent": "info_provided", "confidence": 0.30},
                {"intent": "agreement", "confidence": 0.15}
            ]
        },
        "priority": 1,
        "require_context": {},
    },

    # ─────────────────────────────────────────────
    # idx 3: "Да" после предложения демо — high-value, context-matched
    # ─────────────────────────────────────────────
    {
        "message": "Да",
        "context": {"last_action": "предложил демо"},
        "result": {
            "intent": "demo_request",
            "confidence": 0.88,
            "reasoning": "Согласие на демо после предложения",
            "alternatives": [
                {"intent": "agreement", "confidence": 0.75},
                {"intent": "callback_request", "confidence": 0.20}
            ]
        },
        "priority": 2,
        "require_context": {"last_action": "предложил демо"},
    },

    # ─────────────────────────────────────────────
    # idx 4: request_brevity — high-value
    # ─────────────────────────────────────────────
    {
        "message": "не грузите меня, скажите суть",
        "context": {},
        "result": {
            "intent": "request_brevity",
            "confidence": 0.85,
            "reasoning": "Клиент просит краткость, не возражает по сути",
            "alternatives": [
                {"intent": "objection_think", "confidence": 0.45},
                {"intent": "objection_no_time", "confidence": 0.30}
            ]
        },
        "priority": 2,
        "require_context": {},
    },

    # ─────────────────────────────────────────────
    # idx 5: request_brevity variant — conditional, дубль интента → skip при diversity
    # ─────────────────────────────────────────────
    {
        "message": "короче давайте, хватит воды",
        "context": {},
        "result": {
            "intent": "request_brevity",
            "confidence": 0.90,
            "reasoning": "Запрос на краткость и конкретику",
            "alternatives": [
                {"intent": "objection_no_time", "confidence": 0.35},
                {"intent": "rejection", "confidence": 0.20}
            ]
        },
        "priority": 3,
        "require_context": {},
    },

    # ─────────────────────────────────────────────
    # idx 6: Возражение конкурент — anchor
    # ─────────────────────────────────────────────
    {
        "message": "у нас Poster, зачем нам вы?",
        "context": {},
        "result": {
            "intent": "objection_competitor",
            "confidence": 0.96,
            "reasoning": "Клиент упоминает конкурента Poster как причину отказа",
            "alternatives": [
                {"intent": "comparison", "confidence": 0.40},
                {"intent": "rejection", "confidence": 0.25}
            ]
        },
        "priority": 1,
        "require_context": {},
    },

    # ─────────────────────────────────────────────
    # idx 7: "давайте оформим" в negotiation — high-value, context-matched
    # ─────────────────────────────────────────────
    {
        "message": "давайте оформим",
        "context": {"state": "autonomous_negotiation"},
        "result": {
            "intent": "agreement",
            "confidence": 0.95,
            "reasoning": "Клиент готов оформить сделку — прямое согласие",
            "alternatives": [
                {"intent": "demo_request", "confidence": 0.20},
            ]
        },
        "priority": 2,
        "require_context": {"state": "autonomous_negotiation"},
    },

    # ─────────────────────────────────────────────
    # idx 8: "ладно, давайте" после демо — high-value, context-matched
    # ─────────────────────────────────────────────
    {
        "message": "ладно, давайте",
        "context": {"last_action": "предложил демо"},
        "result": {
            "intent": "demo_request",
            "confidence": 0.82,
            "reasoning": "Неуверенное согласие на демо",
            "alternatives": [
                {"intent": "agreement", "confidence": 0.78},
                {"intent": "objection_think", "confidence": 0.25}
            ]
        },
        "priority": 2,
        "require_context": {"last_action": "предложил демо"},
    },

    # ─────────────────────────────────────────────
    # idx 9: Контакты — anchor
    # ─────────────────────────────────────────────
    {
        "message": "+7 999 123 45 67",
        "context": {},
        "result": {
            "intent": "contact_provided",
            "confidence": 0.99,
            "reasoning": "Клиент оставил номер телефона",
            "extracted_data": {
                "contact_info": "+7 999 123 45 67"
            },
            "alternatives": [
                {"intent": "callback_request", "confidence": 0.20},
                {"intent": "info_provided", "confidence": 0.10}
            ]
        },
        "priority": 1,
        "require_context": {},
    },

    # ─────────────────────────────────────────────
    # idx 10: Rejection — anchor
    # ─────────────────────────────────────────────
    {
        "message": "Нет, нам не интересно",
        "context": {},
        "result": {
            "intent": "rejection",
            "confidence": 0.92,
            "reasoning": "Категоричный отказ без объяснения причины",
            "alternatives": [
                {"intent": "objection_no_need", "confidence": 0.55},
                {"intent": "farewell", "confidence": 0.20}
            ]
        },
        "priority": 1,
        "require_context": {},
    },

    # ─────────────────────────────────────────────
    # idx 11: objection_timing — high-value
    # ─────────────────────────────────────────────
    {
        "message": "не сейчас",
        "context": {},
        "result": {
            "intent": "objection_timing",
            "confidence": 0.70,
            "reasoning": "Отложенный интерес, не полный отказ",
            "alternatives": [
                {"intent": "rejection", "confidence": 0.55},
                {"intent": "objection_no_time", "confidence": 0.50}
            ]
        },
        "priority": 2,
        "require_context": {},
    },

    # ─────────────────────────────────────────────
    # idx 12: Возражение по цене — anchor
    # ─────────────────────────────────────────────
    {
        "message": "Это слишком дорого для нас",
        "context": {},
        "result": {
            "intent": "objection_price",
            "confidence": 0.95,
            "reasoning": "Возражение по цене, не вопрос",
            "alternatives": [
                {"intent": "rejection", "confidence": 0.30},
                {"intent": "objection_no_need", "confidence": 0.20}
            ]
        },
        "priority": 1,
        "require_context": {},
    },

    # ─────────────────────────────────────────────
    # idx 13: Bare name "Султан" — high-value, context-matched
    # ─────────────────────────────────────────────
    {
        "message": "Султан",
        "context": {"last_action": "autonomous_respond", "spin_phase": "discovery"},
        "result": {
            "intent": "info_provided",
            "confidence": 0.85,
            "reasoning": "Короткий ответ — имя в ответ на вопрос бота",
            "extracted_data": {"contact_name": "Султан"},
            "alternatives": [
                {"intent": "greeting", "confidence": 0.40},
                {"intent": "situation_provided", "confidence": 0.20}
            ]
        },
        "priority": 2,
        "require_context": {"spin_phase": "discovery"},
    },

    # ─────────────────────────────────────────────
    # idx 14: SPIN проблема — high-value, context-matched
    # ─────────────────────────────────────────────
    {
        "message": "Постоянно теряем клиентов из-за того что забываем перезвонить",
        "context": {"spin_phase": "problem"},
        "result": {
            "intent": "problem_revealed",
            "confidence": 0.94,
            "reasoning": "Клиент раскрывает боль - потеря клиентов",
            "extracted_data": {
                "pain_point": "теряем клиентов",
                "pain_category": "losing_clients"
            },
            "alternatives": [
                {"intent": "situation_provided", "confidence": 0.35},
                {"intent": "info_provided", "confidence": 0.20}
            ]
        },
        "priority": 2,
        "require_context": {"spin_phase": "problem"},
    },

    # ─────────────────────────────────────────────
    # idx 15: "3 точки" как ответ в discovery — high-value, context-matched
    # ─────────────────────────────────────────────
    {
        "message": "3 точки",
        "context": {"spin_phase": "discovery"},
        "result": {
            "intent": "situation_provided",
            "confidence": 0.90,
            "reasoning": "Клиент отвечает на вопрос бота о количестве точек",
            "extracted_data": {"company_size": 3},
            "alternatives": [
                {"intent": "info_provided", "confidence": 0.40},
                {"intent": "price_question", "confidence": 0.15}
            ]
        },
        "priority": 2,
        "require_context": {"spin_phase": "discovery"},
    },

    # ─────────────────────────────────────────────
    # idx 16: "подумаю" в presentation — high-value, context-matched
    # ─────────────────────────────────────────────
    {
        "message": "подумаю",
        "context": {"spin_phase": "presentation"},
        "result": {
            "intent": "objection_think",
            "confidence": 0.82,
            "reasoning": "Клиент берёт паузу, не отказывает полностью",
            "alternatives": [
                {"intent": "objection_timing", "confidence": 0.50},
                {"intent": "rejection", "confidence": 0.25}
            ]
        },
        "priority": 2,
        "require_context": {"spin_phase": "presentation"},
    },

    # ─────────────────────────────────────────────
    # idx 17: "Да, всё устраивает" в closing — high-value, context-matched
    # ─────────────────────────────────────────────
    {
        "message": "Да, всё устраивает",
        "context": {"state": "autonomous_closing"},
        "result": {
            "intent": "agreement",
            "confidence": 0.93,
            "reasoning": "Клиент подтверждает готовность в фазе закрытия",
            "alternatives": [
                {"intent": "demo_request", "confidence": 0.15},
                {"intent": "gratitude", "confidence": 0.10}
            ]
        },
        "priority": 2,
        "require_context": {"state": "autonomous_closing"},
    },

    # ─────────────────────────────────────────────
    # idx 18: problem_revealed "расхождения остатков" — high-value, context-matched
    # ─────────────────────────────────────────────
    {
        "message": "постоянные расхождения остатков между складом и кассой",
        "context": {"spin_phase": "discovery"},
        "result": {
            "intent": "problem_revealed",
            "confidence": 0.92,
            "reasoning": "Клиент описывает конкретную боль — расхождение учёта",
            "extracted_data": {
                "pain_point": "расхождения остатков",
                "pain_category": "inventory_mismatch"
            },
            "alternatives": [
                {"intent": "situation_provided", "confidence": 0.40},
                {"intent": "info_provided", "confidence": 0.20}
            ]
        },
        "priority": 2,
        "require_context": {"spin_phase": "discovery"},
    },
]


def get_relevant_few_shot_examples(n: int, context: dict = None) -> list:
    """Контекстно-зависимый отбор few-shot примеров.

    Алгоритм:
      1. Anchors (priority=1) — всегда включены
      2. Context-matched — примеры, чей require_context совпадает с текущим контекстом
      3. Diversity fill — по одному примеру на интент, ещё не представленный

    Порядок примеров в FEW_SHOT_EXAMPLES больше не важен.
    """
    context = context or {}

    anchors = [e for e in FEW_SHOT_EXAMPLES if e.get("priority") == 1]

    def context_match(ex):
        rc = ex.get("require_context", {})
        if not rc:
            return False
        return any(context.get(k) == v for k, v in rc.items())

    context_matched = [
        e for e in FEW_SHOT_EXAMPLES
        if e not in anchors and context_match(e)
    ]

    remaining = [
        e for e in FEW_SHOT_EXAMPLES
        if e not in anchors and e not in context_matched
    ]

    selected = list(anchors)
    seen_intents = {e["result"]["intent"] for e in selected}

    for pool in [context_matched, remaining]:
        for e in pool:
            if len(selected) >= n:
                break
            intent = e["result"]["intent"]
            if intent not in seen_intents:
                selected.append(e)
                seen_intents.add(intent)

    # Если ещё есть место — добавляем дубли интентов из context_matched
    if len(selected) < n:
        for e in context_matched:
            if len(selected) >= n:
                break
            if e not in selected:
                selected.append(e)

    return selected[:n]


def get_few_shot_prompt(n_examples: int = 12, context: dict = None) -> str:
    """Контекстно-зависимые few-shot примеры для промпта.

    Args:
        n_examples: Максимальное число примеров (из settings.yaml: classifier.n_few_shot)
        context: Контекст диалога для context-aware отбора
    """
    import json

    examples = get_relevant_few_shot_examples(n_examples, context)

    parts = ["## Примеры классификации:\n"]

    for i, ex in enumerate(examples, 1):
        parts.append(f"### Пример {i}:")
        parts.append(f"Сообщение: {ex['message']}")
        if ex['context']:
            parts.append(f"Контекст: {ex['context']}")
        parts.append(f"Ответ: {json.dumps(ex['result'], ensure_ascii=False)}\n")

    return "\n".join(parts)
