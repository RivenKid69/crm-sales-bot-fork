"""Few-shot примеры для LLM классификатора."""

FEW_SHOT_EXAMPLES = [
    # Приветствия
    {
        "message": "Привет!",
        "context": {},
        "result": {
            "intent": "greeting",
            "confidence": 0.98,
            "reasoning": "Стандартное приветствие"
        }
    },
    {
        "message": "Здравствуйте, хотел бы узнать о вашем продукте",
        "context": {},
        "result": {
            "intent": "greeting",
            "confidence": 0.95,
            "reasoning": "Приветствие с намерением узнать больше"
        }
    },

    # Ценовые
    {
        "message": "Сколько стоит ваша система?",
        "context": {},
        "result": {
            "intent": "price_question",
            "confidence": 0.97,
            "reasoning": "Прямой вопрос о цене"
        }
    },
    {
        "message": "Это слишком дорого для нас",
        "context": {},
        "result": {
            "intent": "objection_price",
            "confidence": 0.95,
            "reasoning": "Возражение по цене, не вопрос"
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
            }
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
            }
        }
    },

    # Короткие ответы с контекстом
    {
        "message": "Да",
        "context": {"last_action": "предложил демо"},
        "result": {
            "intent": "demo_request",
            "confidence": 0.90,
            "reasoning": "Согласие на демо после предложения"
        }
    },
    {
        "message": "Да",
        "context": {"last_action": "спросил про проблемы"},
        "result": {
            "intent": "agreement",
            "confidence": 0.85,
            "reasoning": "Подтверждение наличия проблем"
        }
    },

    # Возражения vs rejection
    {
        "message": "Нет, нам не интересно",
        "context": {},
        "result": {
            "intent": "rejection",
            "confidence": 0.92,
            "reasoning": "Категоричный отказ без объяснения причины"
        }
    },
    {
        "message": "Нет, у нас уже есть iiko",
        "context": {},
        "result": {
            "intent": "objection_competitor",
            "confidence": 0.94,
            "reasoning": "Отказ с указанием конкурента"
        }
    },

    # Контакты
    {
        "message": "+7 999 123 45 67",
        "context": {},
        "result": {
            "intent": "contact_provided",
            "confidence": 0.99,
            "reasoning": "Клиент оставил номер телефона",
            "extracted_data": {
                "contact_info": "+7 999 123 45 67"
            }
        }
    },

    # Запрос краткости (request_brevity)
    {
        "message": "не грузите меня, просто скажите суть",
        "context": {},
        "result": {
            "intent": "request_brevity",
            "confidence": 0.95,
            "reasoning": "Клиент просит более краткий ответ, не возражение"
        }
    },
    {
        "message": "короче, давайте по делу",
        "context": {},
        "result": {
            "intent": "request_brevity",
            "confidence": 0.93,
            "reasoning": "Запрос на краткость и конкретику"
        }
    },

    # Конкуренты (objection_competitor)
    {
        "message": "у нас Poster, зачем нам вы?",
        "context": {},
        "result": {
            "intent": "objection_competitor",
            "confidence": 0.96,
            "reasoning": "Клиент упоминает конкурента Poster как причину отказа"
        }
    },
    {
        "message": "мы уже используем iiko",
        "context": {},
        "result": {
            "intent": "objection_competitor",
            "confidence": 0.94,
            "reasoning": "Клиент указывает на использование конкурентного продукта"
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
