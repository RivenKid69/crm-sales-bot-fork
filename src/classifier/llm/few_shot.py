"""Few-shot примеры для LLM классификатора с alternatives."""

FEW_SHOT_EXAMPLES = [
    # Приветствия - однозначное
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
        }
    },

    # Ценовой вопрос с контекстом количества точек — price_question, НЕ situation_provided
    {
        "message": "Сколько будет стоить на 5 точек?",
        "context": {"spin_phase": "discovery"},
        "result": {
            "intent": "price_question",
            "confidence": 0.93,
            "reasoning": "Клиент спрашивает стоимость для конкретного масштаба — это ценовой вопрос",
            "alternatives": [
                {"intent": "situation_provided", "confidence": 0.30},
                {"intent": "pricing_details", "confidence": 0.25}
            ]
        }
    },

    # Ценовые - однозначное
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
        }
    },

    # Demo/пробный доступ с согласием — первичный intent demo_request, НЕ agreement
    {
        "message": "Хорошо, убедили. Есть демо?",
        "context": {"last_action": "autonomous_respond"},
        "result": {
            "intent": "demo_request",
            "confidence": 0.91,
            "reasoning": "Клиент согласился и сразу спрашивает про демо — главный интент демо",
            "alternatives": [
                {"intent": "agreement", "confidence": 0.55},
                {"intent": "question_features", "confidence": 0.20}
            ]
        }
    },

    # Callback с казахским — не мягкое закрытие
    {
        "message": "Жарайды, байланысайық",
        "context": {"spin_phase": "discovery"},
        "result": {
            "intent": "callback_request",
            "confidence": 0.88,
            "reasoning": "Казахское 'байланысайық' = давайте будем на связи/созвонимся",
            "alternatives": [
                {"intent": "agreement", "confidence": 0.40},
                {"intent": "farewell", "confidence": 0.15}
            ]
        }
    },

    # SPIN ситуация
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
        }
    },

    # ДВУСМЫСЛЕННОЕ - короткий ответ требует контекста
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
        }
    },

    # ДВУСМЫСЛЕННОЕ - request_brevity vs objection_think (ключевой кейс!)
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
        }
    },

    # ДВУСМЫСЛЕННОЕ - хватит болтать (должен поймать даже без точного примера)
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
        }
    },

    # Возражение конкурент - однозначное
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
        }
    },

    # ДВУСМЫСЛЕННОЕ - "ладно" может быть разным
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
        }
    },

    # Контакты - однозначное
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
        }
    },

    # Rejection vs objection - важное различие
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
        }
    },

    # ДВУСМЫСЛЕННОЕ - "не сейчас"
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
        }
    },

    # Возражение по цене - однозначное
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
        }
    },

    # Bare name — ответ на вопрос бота, НЕ приветствие
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
        }
    },

    # SPIN проблема
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
        }
    },
]


def get_few_shot_prompt(n_examples: int = 5) -> str:
    """Получить few-shot примеры для промпта."""
    import json

    examples = FEW_SHOT_EXAMPLES[:n_examples]

    parts = ["## Примеры классификации:\n"]

    for i, ex in enumerate(examples, 1):
        parts.append(f"### Пример {i}:")
        parts.append(f"Сообщение: {ex['message']}")
        if ex['context']:
            parts.append(f"Контекст: {ex['context']}")
        parts.append(f"Ответ: {json.dumps(ex['result'], ensure_ascii=False)}\n")

    return "\n".join(parts)
