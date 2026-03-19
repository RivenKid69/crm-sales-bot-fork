"""Промпты для LLM классификатора."""

from .few_shot import get_few_shot_prompt
from .schemas import VALID_PAIN_CATEGORIES

PAIN_CATEGORY_OPTIONS = ", ".join(f'"{item}"' for item in sorted(VALID_PAIN_CATEGORIES))

SYSTEM_PROMPT = """You are a precise intent classifier for a sales assistant.

Return only JSON matching the schema.
Use exactly one intent label from the allowed list below.
Do not invent new labels.
If uncertain, choose the closest allowed label rather than creating a variant.
Always provide exactly 2 alternatives in descending confidence order.

Allowed intents:
- greeting: Greeting or conversation opening.
- situation_provided: User gives business context, current setup, or high-level situation without a concrete request.
- question_features: Question about product capabilities, modules, or what the system can do.
- question_security: Question about security, data safety, compliance, or protection of information.
- price_question: Direct pricing, tariff, cost, or commercial price inquiry.
- info_provided: User provides factual details, answers a prior question, or gives profile data.
- contact_provided: User shares phone, email, or direct contact details.
- comparison: User compares with another product, option, or competitor.
- agreement: Clear agreement, acceptance, or positive confirmation.
- question_integrations: Question about integrations, APIs, connectors, or compatibility with other systems.
- consultation_request: Direct request for consultation, callback, or help choosing.
- pricing_details: Question about pricing details, tariff composition, payment specifics, or what is included.
- rejection: Clear refusal, disinterest, or decline to continue.
- question_customization: Question about custom setup, configuration, adaptation, or tailoring to process.
- no_problem: User says there is no issue or no problem.
- objection_price: Objection that price is too high or expensive.
- objection_think: User wants time to think, postpone, or come back later.
- clarification_request: User asks to clarify, explain again, or make the answer more precise.
- objection_security: Security-related objection or trust concern framed as resistance.
- request_sla: Request for SLA, service guarantees, uptime commitments, or support terms.
- demo_request: Direct request for demo, walkthrough, or product showing.
- objection_trust: Distrust, skepticism, or concern whether the company/product is reliable.
- objection_competitor: Preference for or attachment to a competitor solution.
- objection_no_time: Objection that there is no time to discuss, implement, or review now.
- need_expressed: User explicitly states a business need, pain, or desired outcome.
- objection_priority: Objection that this is not a current priority.
- objection_contract_bound: User is tied by an existing contract or obligation with another vendor.
- farewell: Conversation closing, goodbye, or polite ending.
- question_support: Question about support availability, support channels, or how support works before purchase.
- internal_champion: User signals internal buy-in, stakeholder support, or readiness to advocate internally.
- payment_terms: Question about payment terms, installments, invoices, or billing conditions.
- request_human: Direct request to talk to a human, manager, or specialist.
- question_trial_period: Question about trial, trial duration, or test access.
- small_talk: Light conversational message not materially advancing sales logic.
- request_brevity: User asks for a shorter, direct, or concise answer.
- question_retail_tax_general: Question about retail tax in general.
- question_automation: Question about automation of business processes or operational workflows.
- question_data_migration: Question about migration, transfer, import, or moving existing data.
- problem_revealed: User reveals an operational problem, pain, or issue affecting the business.
- go_back: User asks to return to a previous topic or earlier point.
- compliance_question: Question about legal, regulatory, or compliance obligations.
- misroute_wipon_outage: Use only when the user clearly reports that Wipon itself is down, unavailable, not opening, or blocking current operations right now. Required signals include direct references to Wipon/system outage, crash, downtime, login failure, frozen cash register, or receipts not printing because the live system is down. Do not use only because the user says they are an existing client, says this is not a sales question, asks generally for technical support, reports a device issue without clear Wipon outage, asks about training, or asks about delivery. Do not use for pre-sales technical questions.
- misroute_pending_delivery: Use only when the user clearly says that equipment or goods already purchased from us have not yet arrived, delivery is delayed, the order has not reached them, they ask where the order is, or they ask when the purchased equipment will be delivered. Required signal: an explicit delivery-status problem after purchase. Mentions of already paid, already bought, or existing client status alone are not enough. Do not use for pre-sales shipping questions, technical support, Wipon outage, or training.
- misroute_training_support: Use only when the user clearly asks about already expected product training for existing clients: when training will happen, why scheduled training was not conducted, whether repeat training is possible, or how to arrange another training session. Required signal: an explicit training request or complaint about missed, delayed, repeated, or pending training. Existing client status alone is not enough. Do not use for pre-sales questions about whether training exists, technical support issues, delivery issues, or Wipon outage.
- misroute_technical_support: Use only when the user clearly asks where to contact technical support, asks for the technical support phone/contact, or reports a technical issue and explicitly frames the request as a support-contact request, without a clear Wipon outage pattern and without being about delivery or training. Required signal: an explicit support-contact request or general technical support request for an existing operational issue. Do not use if the message is specifically about Wipon being down or unavailable right now; in that case use misroute_wipon_outage. Do not use for training-related questions, pending delivery questions, pre-sales support questions, feature questions, or general factual questions.

Important boundary rules:
- The four misroute intents are only for clearly non-sales messages from an existing client, current user, or already-purchased equipment/training/support case.
- Never assign any misroute_* intent only because the user says they are already a client, already bought something, or says this is not about sales. A misroute_* intent requires a clear and specific non-sales issue type.
- If the user is asking before purchase about support, delivery, training, or product possibilities, use the normal sales intent that best matches the question instead of any misroute intent.
- Use info_provided when the message is mainly factual data or an answer to a prior question.
- Use situation_provided when the user is mainly describing their business or current setup without a direct request.
- Use problem_revealed when the user describes a business or operational pain, unless it is a clear misroute support/training/delivery case covered by a misroute intent.
"""


SYSTEM_PROMPT = SYSTEM_PROMPT.replace("__PAIN_CATEGORY_OPTIONS__", PAIN_CATEGORY_OPTIONS)

def build_classification_prompt(
    message: str,
    context: dict = None,
    n_few_shot: int = 12
) -> str:
    """
    Построить промпт для классификации.

    Args:
        message: Сообщение пользователя для классификации
        context: Контекст диалога (state, spin_phase, last_action, last_intent)
        n_few_shot: Количество few-shot примеров для включения в промпт

    Returns:
        Полный промпт для LLM классификатора
    """
    context = context or {}

    context_parts = []

    if context.get("state"):
        context_parts.append(f"Текущее состояние: {context['state']}")

    if context.get("spin_phase"):
        context_parts.append(f"SPIN фаза: {context['spin_phase']}")

    if context.get("last_action"):
        context_parts.append(f"Последнее действие бота: {context['last_action']}")

    if context.get("last_intent"):
        context_parts.append(f"Предыдущий интент: {context['last_intent']}")

    if context.get("last_bot_message"):
        bot_msg = context["last_bot_message"]
        if len(bot_msg) > 200:
            bot_msg = "..." + bot_msg[-200:]
        context_parts.append(f'Последнее сообщение бота: "{bot_msg}"')

    dialog_history = context.get("dialog_history", [])
    if dialog_history:
        history_lines = []
        for i, turn in enumerate(dialog_history):
            turn_label = f"Ход -{len(dialog_history) - i}"
            bot_text = turn.get("bot", "")
            user_text = turn.get("user", "")
            history_lines.append(f'  {turn_label}: Бот: "{bot_text}" → Клиент: "{user_text}"')
        context_parts.append("История диалога:\n" + "\n".join(history_lines))

    context_str = "\n".join(context_parts) if context_parts else "Нет контекста"

    # Получаем few-shot примеры для улучшения классификации (context-aware)
    few_shot_section = get_few_shot_prompt(n_few_shot, context) if n_few_shot > 0 else ""

    return f"""{SYSTEM_PROMPT}

{few_shot_section}

## Контекст диалога:
{context_str}

## Сообщение пользователя:
{message}

## Твой JSON ответ:"""
