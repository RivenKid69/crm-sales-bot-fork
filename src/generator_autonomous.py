"""Autonomous helpers extracted from generator.py."""

from typing import Any, Dict, List, Optional, Tuple
import re

# Hallucination guard: intents requiring KB facts (prefix-based + explicit)
KB_GUARD_FACTUAL_INTENTS_EXPLICIT: set = {
    "price_question", "pricing_details", "cost_inquiry",
    "pricing_comparison", "comparison",
    "request_proposal", "request_invoice", "request_contract",
    "request_sla", "request_references",
    "roi_question", "case_study_request",
    "company_info_question", "experience_question",
}
KB_GUARD_ACTIONS: set = {"autonomous_respond", "continue_current_goal"}

# Template variables that must always be present before prompt rendering.
CRITICAL_TEMPLATE_VARS = {"system", "user_message", "history", "retrieved_facts"}

# Actions that reach generator.generate() via the else-branch in bot.py and
# should surface a secondary price answer via blocking_with_pricing template.
BLOCKING_ACTIONS_FOR_SECONDARY_INJECT: frozenset = frozenset({
    "objection_limit_reached",
    "go_back_limit_reached",
})

# Guardrails for prompt/rules size in autonomous flow.
MAX_GATED_RULES = 5
MAX_PROMPT_CHARS = 35_000

SAFETY_RULES_V2 = """⛔ КРИТИЧЕСКИЕ ПРАВИЛА (нарушение = провал):
1. ЛЮБАЯ цифра, цена — ТОЛЬКО из БАЗЫ ЗНАНИЙ ниже. Нет в базе → "уточню у коллег". НЕ считай, НЕ округляй.
   Точные цены тарифов: Mini=5000₸/мес, Lite=150000₸/год, Standard=220000₸/год, Pro=500000₸/год. НЕ ПУТАЙ тариф и цену.
2. Продукт = WIPON. Не упоминай WMS, 1C, Битрикс, WisePOS и любые другие системы.
3. Не выдумывай кейсы, названия клиентов, истории, политики компании. Нет в базе = ложь.
   НЕ утверждай что "у нас нет холодных звонков", "звоним только по записи", "только в ответ на обращения".
   Если клиент жалуется на звонки — извинись за неудобство, НЕ отрицай его опыт.
4. Не утверждай что уже отправил/подключил/настроил.
5. Простой текст без форматирования (без **, списков, ссылок). Без примечаний и пояснений к себе.
6. Если клиент задаёт вопрос НЕ о Wipon/POS/бизнесе — скажи "я специализируюсь на Wipon" и верни разговор к его бизнесу."""

HARD_NO_CONTACT_MARKERS: Tuple[str, ...] = (
    "контакты не дам",
    "контакт не дам",
    "контакт пока не даю",
    "пока не даю контакт",
    "не дам контакт",
    "не проси мои контакты",
    "без контакта",
    "без контактов",
    "номер не дам",
    "телефон не дам",
    "без звонков",
    "не звоните",
)

DEFER_CONTACT_MARKERS: Tuple[str, ...] = (
    "потом дам контакт",
    "позже дам контакт",
    "контакт пока не даю",
    "контакт потом",
    "контакт позже",
    "контакт не сейчас",
    "контакт позже дам",
    "телефон потом",
    "телефон позже",
    "номер потом",
    "если ок потом дам контакт",
)

_OBJECTION_4P_INTENTS = {
    "objection_price", "objection_competitor", "objection_no_time",
    "objection_timing", "objection_complexity",
}


def build_autonomous_objection_instructions(intent: str) -> str:
    """Build objection-specific instructions for autonomous flow response."""
    objection_type = intent.replace("objection_", "").replace("_", " ")

    if intent in _OBJECTION_4P_INTENTS:
        return f"""=== ОБРАБОТКА ВОЗРАЖЕНИЯ: {objection_type} ===
Клиент выразил рациональное возражение. Используй подход 4P:
1. ПАУЗА — признай опасения клиента, покажи что понимаешь
2. УТОЧНЕНИЕ — задай уточняющий вопрос чтобы понять корень возражения
3. ПРЕЗЕНТАЦИЯ ЦЕННОСТИ — приведи конкретный аргумент из базы знаний
4. ПРОДВИЖЕНИЕ — предложи следующий шаг (демо, расчёт ROI, тест)
Отработай возражение мягко, без давления. Используй данные из базы знаний."""
    return f"""=== ОБРАБОТКА ВОЗРАЖЕНИЯ: {objection_type} ===
Клиент выразил эмоциональное возражение. Используй подход 3F:
1. FEEL — покажи что понимаешь чувства клиента ("Да, это важный момент...")
2. FELT — приведи социальное доказательство ("Многие клиенты изначально думали так же...")
3. FOUND — покажи результат ("Но после внедрения они отметили...")
Проявляй эмпатию. Не спорь с эмоциями. Приведи конкретный пример из базы знаний."""


def build_state_gated_rules(
    state: str,
    intent: str,
    user_message: str,
    history: List[Dict[str, Any]],
    collected: Dict[str, Any],
    secondary_intents: Optional[List[str]] = None,
) -> str:
    """Build Layer-2 rules that appear only when state/intent makes them relevant."""
    _ = collected
    rules: List[Tuple[int, str]] = []
    state_value = str(state or "")
    intent_value = str(intent or "")
    message_lower = str(user_message or "").lower()
    is_autonomous_context = state_value.startswith("autonomous_") or state_value == "greeting"

    history_tail = history[-4:] if isinstance(history, list) else []
    history_user_lower = " ".join(
        str(turn.get("user", "") or "")
        for turn in history_tail
        if isinstance(turn, dict)
    ).lower()
    secondary_set = {str(i) for i in (secondary_intents or []) if i}

    if state_value == "autonomous_closing":
        rules.append((1,
            "⚠️ ИИН: Если клиент даёт ИИН, не повторяй 12-значное число в ответе — "
            "подтверди фразой «ИИН получен». Если клиент ИИН не давал — не придумывай и не подтверждай выдуманные цифры."
        ))

    discount_keywords = ("скидку", "скидка", "скидок", "скидки", "дешевле", "акция", "акции")
    discount_triggered = (
        intent_value == "request_discount"
        or any(keyword in message_lower for keyword in discount_keywords)
    )
    if discount_triggered:
        rules.append((3,
            "⚠️ СКИДКИ: не придумывай индивидуальные акции или проценты. "
            "Если в БАЗЕ ЗНАНИЙ нет точных условий скидки, скажи: "
            "«Актуальные условия скидок уточнит менеджер»."
        ))

    competitor_names = ("iiko", "poster", "r-keeper", "1с", "1c", "умаг", "beksar", "paloma")
    price_concession_words = ("дороже", "дешевле", "цена", "стоимость")
    has_competitor_context = any(
        name in message_lower or name in history_user_lower
        for name in competitor_names
    )
    has_price_concession = any(word in message_lower for word in price_concession_words)
    if has_competitor_context and has_price_concession:
        rules.append((3,
            "⚠️ КОНКУРЕНТЫ: не придумывай сравнительные цифры по конкурентам. "
            "Если в БАЗЕ ЗНАНИЙ нет точного сравнения цен/условий — признай это и предложи "
            "уточнить детали у менеджера."
        ))

    explicit_buy_markers = (
        "готов покупать",
        "готов купить",
        "хочу купить",
        "выставляйте счет",
        "выставьте счет",
        "выставь счет",
        "хочу счет",
        "счёт выставляйте",
        "оплачу",
        "как оплатить",
        "оформим",
        "оформляйте",
    )
    if (
        is_autonomous_context
        and state_value != "autonomous_closing"
        and any(marker in message_lower for marker in explicit_buy_markers)
    ):
        rules.append((1,
            "⚠️ КЛИЕНТ ГОТОВ ПОКУПАТЬ: не возвращайся в discovery/квалификацию. "
            "Подтверди готовность, коротко опиши следующий шаг и мягко переведи к оформлению "
            "(контакт/счёт), без лишних вопросов о бизнесе или боли."
        ))

    hard_no_contact = (
        is_autonomous_context
        and has_hard_no_contact_signal(
            user_message=user_message,
            history=history,
        )
    )
    soft_no_contact = (
        is_autonomous_context
        and not hard_no_contact
        and has_contact_boundary_signal(
            user_message=user_message,
            history=history,
            include_deferred=True,
        )
    )

    exit_risk_markers = ("выйти", "выход", "расторг", "если не подойдет", "если не подойд")
    exit_contract_triggered = is_autonomous_context and (
        intent_value in {"objection_risk", "objection_contract_bound"}
        or any(marker in message_lower for marker in exit_risk_markers)
    )

    if hard_no_contact and not exit_contract_triggered:
        rules.append((2,
            "⚠️ NO-CONTACT (HARD): формат 1-2 предложения, один self-serve шаг, "
            "без абсолютов/гарантий, без запроса контактов."
        ))
    elif soft_no_contact:
        rules.append((2,
            "⚠️ NO-CONTACT (SOFT): не запрашивай телефон/email повторно. "
            "Дай полезный следующий шаг."
        ))

    if is_autonomous_context and (
        intent_value in {"request_sla", "request_references", "question_security", "question_integrations"}
        or any(k in message_lower for k in ("sla", "rpo", "rto", "шифрован", "безопас", "аудит"))
    ):
        rules.append((2,
            "⚠️ ТЕХНИЧЕСКИЕ ФАКТЫ: отвечай только тем, что есть в БАЗЕ ЗНАНИЙ. "
            "Если конкретного параметра нет (SLA, RPO/RTO, стандарты) — прямо скажи, что уточнишь."
        ))

    integration_markers = ("интеграц", "kaspi", "api", "1с", "amo", "bitrix", "crm", "whatsapp")
    explicit_price_markers = ("цена", "стоимость", "тариф", "сколько стоит", "в тенге", "тг", "₸")
    asks_integration = intent_value in {"question_integrations", "question_features"} or any(
        m in message_lower for m in integration_markers
    )
    asks_price = intent_value in {"price_question", "pricing_details", "pricing_comparison"} or any(
        m in message_lower for m in explicit_price_markers
    )
    if asks_integration and not asks_price:
        rules.append((3,
            "⚠️ TOPIC-LOCK: клиент спрашивает про интеграции/функции. "
            "Отвечай по теме интеграций. Не уводи ответ в цену, если цену не спрашивали."
        ))

    compare_markers = (
        "сравни", "сравнение", "чем лучше", "чем отличается", "vs", "против",
        "плюсы", "минусы", "альтернатива", "конкурент",
    )
    comparison_requested = (
        intent_value in {"comparison", "pricing_comparison", "question_tariff_comparison"}
        or bool({"comparison", "pricing_comparison", "question_tariff_comparison"} & secondary_set)
        or any(m in message_lower for m in compare_markers)
    )
    if comparison_requested:
        rules.append((2,
            "⚠️ СРАВНЕНИЕ: отвечай структурно (2-4 критерия: функционал, интеграции, стоимость, внедрение) "
            "и только по фактам из БАЗЫ ЗНАНИЙ. Если по одному из критериев фактов нет — так и скажи, не додумывай."
        ))

    interruption_secondary = {
        i for i in secondary_set
        if i.startswith("question_") or i in {"comparison", "pricing_comparison"}
    }
    interruption_primary = (
        intent_value.startswith("question_")
        or intent_value in {"comparison", "pricing_comparison"}
    )
    if (
        is_autonomous_context
        and state_value != "autonomous_closing"
        and not comparison_requested
        and (interruption_primary or interruption_secondary)
    ):
        rules.append((2,
            "⚠️ INTERRUPTION: клиент перебил этап новым вопросом. "
            "Сначала дай прямой ответ на текущий вопрос по фактам БАЗЫ ЗНАНИЙ, "
            "затем одной короткой фразой вернись к цели этапа. "
            "Не игнорируй вопрос и не перескакивай сразу в сбор контакта/закрытие."
        ))

    if exit_contract_triggered:
        exit_rule = (
            "⚠️ EXIT/CONTRACT: не обещай «без штрафов», «без потери данных», сроки теста или иные гарантии, "
            "если этого нет в БАЗЕ ЗНАНИЙ. Если точных условий нет — скажи: "
            "«Уточню у коллег и вернусь с ответом»."
        )
        if hard_no_contact:
            exit_rule += (
                " HARD NO-CONTACT: формат 1-2 предложения, один self-serve шаг, "
                "без абсолютов/гарантий и без запроса контактов."
            )
        rules.append((1, exit_rule))

    logic_markers = (
        "как связано", "в чем связь", "почему", "за счет чего",
        "что будет если", "как влияет", "зависит ли",
    )
    asks_logic = (
        any(m in message_lower for m in logic_markers)
        or ("если" in message_lower and " то " in message_lower)
    )
    if asks_logic:
        rules.append((3,
            "⚠️ ЛОГИЧЕСКАЯ СВЯЗЬ: если клиент просит объяснить зависимость/причину, "
            "свяжи минимум 2 релевантных факта из БАЗЫ ЗНАНИЙ в формате «факт → следствие». "
            "Если связи нет в фактах — честно укажи, что это нужно уточнить."
        ))

    if not rules:
        return ""

    rules.sort(key=lambda rule: rule[0])
    rules = rules[:MAX_GATED_RULES]
    formatted = "\n".join(f"- {rule[1]}" for rule in rules)
    return f"STATE-GATED ПРАВИЛА:\n{formatted}"


def should_suppress_followup_question_for_interrupt(
    state: str,
    intent: str,
    user_message: str,
    secondary_intents: Optional[List[str]] = None,
) -> bool:
    """Return True when bot should answer interruption without adding a new follow-up question."""
    state_value = str(state or "")
    if not state_value.startswith("autonomous_") or state_value == "autonomous_closing":
        return False

    intent_value = str(intent or "")
    secondary_set = {str(i) for i in (secondary_intents or []) if i}
    has_question_intent = (
        intent_value.startswith("question_")
        or intent_value in {"comparison", "pricing_comparison", "question_tariff_comparison"}
        or any(i.startswith("question_") for i in secondary_set)
        or bool({"comparison", "pricing_comparison", "question_tariff_comparison"} & secondary_set)
    )
    if has_question_intent:
        return True

    message_lower = str(user_message or "").lower()
    logic_markers = (
        "как связано", "в чем связь", "почему", "за счет чего",
        "что будет если", "как влияет", "зависит ли",
    )
    return any(m in message_lower for m in logic_markers) or (
        "если" in message_lower and " то " in message_lower
    )


def has_address_question_in_history(history: list) -> bool:
    """Return True if bot already asked how to address the client."""
    if not isinstance(history, list):
        return False
    markers = (
        "к вам обращаться",
        "как вас зовут",
        "как к вам обращаться",
        "как могу к вам обращаться",
    )
    for turn in history:
        if not isinstance(turn, dict):
            continue
        bot_text = str(turn.get("bot", "") or "").lower()
        if any(m in bot_text for m in markers):
            return True
    return False


def build_address_instruction(
    collected: dict,
    history: Optional[list] = None,
    intent: str = "",
    frustration_level: int = 0,
    state: str = "",
    user_message: str = "",
) -> str:
    """Build conditional address instruction with one-time ask behavior."""
    name = collected.get("contact_name") or collected.get("client_name") or ""
    if name:
        return (
            f'ОБРАЩЕНИЕ: клиента зовут "{name}" — '
            f'используй "господин/госпожа {name}" или "{name}".'
        )

    stressful_intents = {
        "request_brevity",
        "price_question",
        "pricing_details",
        "rejection",
        "rejection_soft",
        "no_need",
        "no_problem",
        "farewell",
    }
    if (
        frustration_level >= 3
        or intent in stressful_intents
        or intent.startswith("objection_")
        or str(state).startswith("autonomous_closing")
    ):
        return (
            "ОБРАЩЕНИЕ: имя клиента неизвестно. НЕ спрашивай имя в этом ответе; "
            "продолжай по сути запроса."
        )

    if str(state).startswith("autonomous_") and intent not in {"greeting", "small_talk"}:
        return (
            "ОБРАЩЕНИЕ: имя клиента неизвестно. Не спрашивай имя; "
            "сфокусируйся на текущем запросе."
        )

    directness_markers = (
        "без воды",
        "коротко",
        "быстрее",
        "по делу",
        "за 1 сообщение",
        "одним сообщением",
        "не задавай вопрос",
        "контакты не дам",
        "контакт не дам",
        "без контактов",
        "без контакта",
        "потом дам контакт",
        "позже дам контакт",
    )
    low_msg = str(user_message or "").lower()
    if any(marker in low_msg for marker in directness_markers):
        return (
            "ОБРАЩЕНИЕ: клиент просит максимально кратко. "
            "Не спрашивай имя в этом ответе."
        )

    if has_address_question_in_history(history or []):
        return (
            "ОБРАЩЕНИЕ: имя клиента неизвестно, но ты уже спрашивал его ранее. "
            "НЕ повторяй вопрос про имя; продолжай диалог по сути."
        )
    return (
        'ОБРАЩЕНИЕ: имя клиента НЕИЗВЕСТНО — один раз мягко вплети '
        '"как к вам обращаться?" в ответ. НЕ придумывай имя/фамилию.'
    )


def build_language_instruction(user_message: str) -> str:
    """Build lightweight language guidance to reduce code-switch degradation."""
    msg = str(user_message or "").lower()
    kz_letters = bool(re.search(r"[әіңғүұқөһ]", msg))
    ru_letters = bool(re.search(r"[а-яё]", msg))
    kz_words = (
        "сәлем", "салем", "бағасы", "қанша", "жоқ", "керек",
        "ұсынасыз", "кейін", "маған", "нақты", "қазақша",
    )
    has_kz_words = sum(1 for w in kz_words if w in msg) >= 2

    if (kz_letters or has_kz_words) and ru_letters:
        return (
            "ЯЗЫК: сообщение смешанное (казахский+русский). "
            "Отвечай ПОНЯТНО на русском (можно вкрапить 1-2 казахских слова по смыслу), "
            "без повторяющихся фраз."
        )
    if kz_letters or has_kz_words:
        return (
            "ЯЗЫК: отвечай на казахском простыми короткими фразами. "
            "Не повторяй одинаковые предложения."
        )
    has_latin = bool(re.search(r"[a-z]", msg))
    translit_markers = (
        "nuzhno", "skolko", "stoit", "to4", "toch", "rabotaet",
        "davai", "bystro", "korotk", "kaspi", "nal", "offline",
    )
    if has_latin and not ru_letters and any(marker in msg for marker in translit_markers):
        return (
            "ЯЗЫК: клиент пишет транслитом. Отвечай простым русским, "
            "коротко (1-2 фразы), без длинных списков и канцелярита."
        )
    return ""


def build_stress_instruction(intent: str, frustration_level: int, user_message: str) -> str:
    """Build brevity/sales focus hint for rushed or high-friction turns."""
    text = str(user_message or "").lower()
    direct_markers = (
        "без воды",
        "по делу",
        "коротко",
        "быстрее",
        "в 1 сообщение",
        "за 1 сообщение",
        "докажи",
    )
    instructions: List[str] = []
    if (
        int(frustration_level or 0) >= 3
        or intent in {"request_brevity", "price_question", "pricing_details"}
        or any(m in text for m in direct_markers)
    ):
        instructions.append(
            "РЕЖИМ КРАТКОСТИ: 1-2 предложения, сначала ключевой факт из БАЗЫ ЗНАНИЙ. "
            "Затем добавь ОДНУ выгоду только если она явно подтверждена фактами. Без лишней воды и "
            "без встречных вопросов, если клиент просит быстрее/кратко."
        )

    contact_refusal_markers = HARD_NO_CONTACT_MARKERS + DEFER_CONTACT_MARKERS
    if any(m in text for m in contact_refusal_markers):
        instructions.append(
            "КОНТАКТ-ОГРАНИЧЕНИЕ: клиент не даёт контакт. НЕ обещай отправить демо/документы "
            "и НЕ обещай счёт/оформление без обязательных данных. "
            "Дай полезный ответ в чате и мягко предложи вернуться к оформлению позже."
        )

    pressure_markers = ("не давит", "не дави", "не настаива", "надо подумать", "дайте подумать", "я подумаю")
    if any(m in text for m in pressure_markers):
        instructions.append(
            "СТОП-ДАВЛЕНИЕ: клиент просит не давить. СТРОГО:\n"
            "- 1 предложение: подтверди что уважаешь решение.\n"
            "- НЕ продавай, НЕ приводи примеры клиентов, НЕ перечисляй функции.\n"
            "- НЕ задавай вопросов.\n"
            "- Пример: 'Понял, если появятся вопросы — пишите, я на связи.'"
        )

    return "\n".join(instructions)


def has_contact_boundary_signal(
    user_message: str,
    history: Optional[list] = None,
    include_deferred: bool = True,
) -> bool:
    """Detect explicit contact refusal or defer signals in current/recent user messages."""
    texts: List[str] = [str(user_message or "").lower()]
    if isinstance(history, list):
        for turn in history[-4:]:
            if isinstance(turn, dict):
                texts.append(str(turn.get("user", "") or "").lower())

    markers: Tuple[str, ...] = HARD_NO_CONTACT_MARKERS
    if include_deferred:
        markers = HARD_NO_CONTACT_MARKERS + DEFER_CONTACT_MARKERS
    return any(marker in text for text in texts for marker in markers)


def has_hard_no_contact_signal(user_message: str, history: Optional[list] = None) -> bool:
    """Detect only hard no-contact signals."""
    return has_contact_boundary_signal(
        user_message=user_message,
        history=history,
        include_deferred=False,
    )


def has_deferred_contact_signal(user_message: str, history: Optional[list] = None) -> bool:
    """Detect deferred contact requests (not hard refusal)."""
    texts: List[str] = [str(user_message or "").lower()]
    if isinstance(history, list):
        for turn in history[-4:]:
            if isinstance(turn, dict):
                texts.append(str(turn.get("user", "") or "").lower())
    return any(marker in text for text in texts for marker in DEFER_CONTACT_MARKERS)


def enforce_no_contact_boundaries(text: str, context: Dict[str, Any]) -> str:
    """Remove contact-push fragments when user explicitly refused to share contacts."""
    user_message = str(context.get("user_message", "") or "")
    history = context.get("history", [])
    if not has_contact_boundary_signal(
        user_message=user_message,
        history=history,
        include_deferred=True,
    ):
        return text

    result = str(text or "")
    patterns = (
        r"(?i)\s*на какой (?:email|номер)[^?.!]*[?.!]",
        r"(?i)\s*остав(?:ьте|ь)(?:,\s*пожалуйста)?[^?.!]{0,40}(?:контакт|номер|телефон|email)[^?.!]*[?.!]",
        r"(?i)\s*(?:пришл(?:ите|и)|напиш(?:ите|и)|укаж(?:ите|и)|дайте)\s*(?:почту|email)[^?.!]*[?.!]",
        r"(?i)\s*(?:пришлю|отправлю|вышлю|скину)[^?.!]{0,50}(?:почт|email)[^?.!]*[?.!]",
        r"(?i)\s*укаж(?:ите|и)\s+пожалуйста,\s*ваш\s*иин[^?.!]*[?.!]",
        r"(?i)\s*как вас набрать[^?.!]*[?.!]",
        r"(?i)\s*менеджер свяжется[^?.!]*[?.!]",
        r"(?i)\s*(?:давайте|предлагаю)\s*(?:созвон|созвониться)[^?.!]*[?.!]",
        r"(?i)\s*(?:удобн\w*)\s*время\s*(?:для\s*)?(?:звонка|созвона)[^?.!]*[?.!]",
    )
    for pat in patterns:
        result = re.sub(pat, " ", result)
    result = re.sub(r"\s+", " ", result).strip()
    if not result:
        return "Понял вас. Дам всю информацию в чате без запроса контактов."
    return result


def format_client_card(collected: dict) -> str:
    """Format collected_data as readable client card for prompts."""
    field_labels = {
        "contact_name": "Контактное лицо",
        "client_name": "Контактное лицо",
        "company_name": "Компания",
        "company_size": "Размер компании (сотрудников)",
        "business_type": "Сфера бизнеса",
        "current_tools": "Текущие инструменты",
        "pain_point": "Основная боль",
        "budget_range": "Бюджет",
        "role": "Должность",
        "timeline": "Сроки",
        "desired_outcome": "Желаемый результат",
        "urgency": "Срочность",
        "users_count": "Кол-во пользователей",
        "preferred_channel": "Канал связи",
        "contact_info": "Контакт",
        "financial_impact": "Финансовые потери",
        "pain_impact": "Влияние проблемы",
    }
    skip_keys = {
        "_dag_results", "_objection_limit_final", "option_index",
        "contact_type", "value_acknowledged", "pain_category",
        "persona", "competitor_mentioned",
    }
    lines: List[str] = []
    for key, value in collected.items():
        if key in skip_keys or value is None:
            continue
        if key == "client_name" and "contact_name" in collected:
            continue
        label = field_labels.get(key, key)
        lines.append(f"  - {label}: {value}")
    return "\n".join(lines) if lines else "(нет данных)"
