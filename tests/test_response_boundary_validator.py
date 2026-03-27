"""Tests for final response boundary validator."""

from unittest.mock import Mock

import pytest

from src.dialog_transcript import DialogTranscript
from src.feature_flags import flags
from src.response_boundary_validator import ResponseBoundaryValidator


@pytest.fixture(autouse=True)
def reset_flags():
    flags.clear_all_overrides()
    flags.set_override("response_boundary_validator", True)
    flags.set_override("response_boundary_retry", True)
    flags.set_override("response_boundary_fallback", True)
    yield
    flags.clear_all_overrides()


def test_pricing_currency_locale_is_canonicalized_to_tenge():
    validator = ResponseBoundaryValidator()
    result = validator.validate_response(
        "Стоимость 15000 руб. или 200₽ в месяц.",
        context={"intent": "price_question", "action": "answer_with_pricing"},
        llm=None,
    )
    assert "руб" not in result.response.lower()
    assert "₽" not in result.response
    assert "₸" in result.response


def test_known_typo_is_fixed_without_retry():
    validator = ResponseBoundaryValidator()
    result = validator.validate_response(
        "Хорошо, присылну ответ сегодня.",
        context={"intent": "info_provided", "action": "continue_current_goal"},
        llm=None,
    )
    assert "присылну" not in result.response.lower()
    assert "пришлю" in result.response.lower()
    assert result.retry_used is False


def test_retry_is_used_once_then_deterministic_fallback():
    validator = ResponseBoundaryValidator()
    llm = Mock()
    llm.generate = Mock(return_value="Оставляю руб и артефакт . — без исправлений")
    validator._sanitize = Mock(side_effect=lambda text, ctx: text)

    result = validator.validate_response(
        "Цена 1000 руб. . — пришлю детали",
        context={"intent": "price_question", "action": "answer_with_pricing_direct"},
        llm=llm,
    )

    assert llm.generate.call_count >= 1
    assert result.retry_used is True
    assert result.fallback_used is True
    assert "руб" not in result.response.lower()
    assert "уточ" in result.response.lower()


def test_semantic_relevance_salvages_dirty_raw_json():
    validator = ResponseBoundaryValidator()
    llm = Mock()
    llm.generate_structured.return_value = None
    llm.generate.return_value = (
        '<think>не по теме</think>'
        '{"relevant": false, "reason": "' + ("Б" * 300) + '",}'
    )

    result = validator._check_semantic_irrelevance(
        "Наш офис находится в Алматы, можем подробнее обсудить адрес.",
        {"intent": "price_question", "user_message": "Расскажите про тариф Lite"},
        llm,
    )

    assert result is True
    llm.generate.assert_called_once()


def test_unknown_source_leak_is_replaced_with_neutral_fallback():
    validator = ResponseBoundaryValidator()
    result = validator.validate_response(
        "В подтвержденных данных нет информации по интеграции с SAP S/4HANA.",
        context={"intent": "question_integrations", "user_message": "Есть интеграция с SAP S/4HANA?"},
        llm=None,
    )
    low = result.response.lower()
    assert "подтвержденных данных" not in low
    assert "нет информации" not in low
    assert "уточ" in low


def test_unknown_source_leak_handles_yo_and_base_knowledge_variants():
    validator = ResponseBoundaryValidator()
    result = validator.validate_response(
        "В базе знаний нет информации о возможности создания white-label приложения под вашим брендом.",
        context={"intent": "question_features", "user_message": "Можно ли сделать white-label приложение?"},
        llm=None,
    )
    low = result.response.lower()
    assert "в базе знаний" not in low
    assert "нет информации" not in low
    assert "уточ" in low


def test_unknown_source_leak_does_not_flag_grounded_product_fact_about_item_base():
    validator = ResponseBoundaryValidator()
    result = validator.validate_response(
        "Лимит номенклатуры в Wipon — ограничений по количеству товаров в базе нет.",
        context={
            "intent": "question_features",
            "user_message": "Есть ограничение по количеству товаров?",
            "retrieved_facts": "Лимит номенклатуры в Wipon — ограничений по количеству товаров в базе нет.",
        },
        llm=None,
    )
    assert result.response == "Лимит номенклатуры в Wipon — ограничений по количеству товаров в базе нет."
    assert "unknown_source_leak" not in result.violations


def test_ungrounded_quant_sanitizer_does_not_leave_orphaned_callback_time_fragment():
    validator = ResponseBoundaryValidator()
    sanitized = validator._sanitize_ungrounded_quant_claim(
        "вам с 9 до 18 часов в удобное время. Напишите, пожалуйста, ваш номер телефона для связи",
        context={
            "intent": "callback_request",
            "state": "autonomous_closing",
            "user_message": "Хорошо, можете перезвонить позже",
            "action": "continue_current_goal",
            "selected_template": "autonomous_respond",
        },
    )

    assert "вам с 9" not in sanitized.lower()
    assert "до 18" not in sanitized.lower()
    assert "номер телефона" not in sanitized.lower()
    assert "в чате" in sanitized.lower()


def test_validate_response_repairs_callback_time_fragment_after_retry():
    validator = ResponseBoundaryValidator()
    llm = Mock()
    llm.generate.return_value = (
        "вам с 9 до 18 часов в удобное время. "
        "Напишите, пожалуйста, ваш номер телефона для связи"
    )

    result = validator.validate_response(
        "Коллега позвонит вам с 9 до 18 часов в удобное время. "
        "Напишите, пожалуйста, ваш номер телефона для связи",
        context={
            "intent": "callback_request",
            "state": "autonomous_closing",
            "user_message": "Хорошо, можете перезвонить позже",
            "action": "continue_current_goal",
            "selected_template": "autonomous_respond",
        },
        llm=llm,
    )

    assert "вам с 9" not in result.response.lower()
    assert "до 18" not in result.response.lower()
    assert "номер телефона" not in result.response.lower()
    assert "email" not in result.response.lower()


def test_hallucination_fallback_keeps_autonomous_callback_in_chat():
    validator = ResponseBoundaryValidator()
    fallback = validator._hallucination_fallback(
        {
            "intent": "callback_request",
            "state": "autonomous_closing",
            "user_message": "Перезвоните мне позже",
            "collected_data": {},
            "violations": ["ungrounded_quant_claim"],
        }
    )

    low = fallback.lower()
    assert "email" not in low
    assert "почт" not in low
    assert "номер телефона" not in low
    assert "в чате" in low


def test_sanitize_demo_without_contact_keeps_autonomous_flow_in_chat():
    validator = ResponseBoundaryValidator()
    sanitized = validator._sanitize_demo_without_contact(
        "Проведу демо без контактных данных.",
        context={
            "state": "autonomous_closing",
            "selected_template": "autonomous_respond",
            "user_message": "Пока без звонка, просто расскажите.",
        },
    )
    low = sanitized.lower()
    assert "номер телефона" not in low
    assert "email" not in low
    assert "в чате" in low


def test_payment_ready_fallback_confirms_purchase_intent():
    validator = ResponseBoundaryValidator()
    fallback = validator._hallucination_fallback(
        {
            "state": "payment_ready",
            "intent": "request_invoice",
            "user_message": "Да, хочу оплатить",
            "violations": ["ungrounded_quant_claim"],
        }
    )
    low = fallback.lower()
    assert "готовы к оплате" in low
    assert "завершить покупку" in low


def test_video_call_terminal_fallback_confirms_call_intent():
    validator = ResponseBoundaryValidator()
    fallback = validator._hallucination_fallback(
        {
            "state": "video_call_scheduled",
            "intent": "demo_request",
            "user_message": "Да, хочу видеозвонок",
            "violations": ["ungrounded_quant_claim"],
        }
    )
    low = fallback.lower()
    assert "видеозвонок нужен" in low
    assert "согласовать время" in low


def test_autonomous_payment_fallback_does_not_request_phone_or_email():
    validator = ResponseBoundaryValidator()
    fallback = validator._hallucination_fallback(
        {
            "state": "autonomous_closing",
            "intent": "payment_confirmation",
            "user_message": "Да, хочу оплатить",
            "selected_template": "autonomous_respond",
            "violations": ["ungrounded_quant_claim"],
        }
    )

    low = fallback.lower()
    assert "номер" not in low
    assert "email" not in low
    assert "оплат" in low


def test_contact_pressure_after_early_refusal_is_detected_from_full_transcript():
    validator = ResponseBoundaryValidator()
    transcript = DialogTranscript.from_legacy_history(
        [
            {"user": "Пока без звонков и без контактов", "bot": "Хорошо, всё дам в чате."},
            {"user": "Расскажите про тарифы", "bot": "Есть Mini, Lite, Standard и Pro."},
            {"user": "А что по Lite?", "bot": "Lite стоит 150 000 ₸/год."},
            {"user": "Спасибо", "bot": "Пожалуйста."},
            {"user": "И еще вопрос", "bot": "Слушаю вас."},
        ]
    )

    result = validator.validate_response(
        "Оставьте, пожалуйста, номер телефона, и я отправлю детали.",
        context={
            "intent": "price_question",
            "state": "autonomous_discovery",
            "selected_template": "autonomous_respond",
            "action": "continue_current_goal",
            "user_message": "Напомните цену Lite",
            "transcript": transcript,
        },
        llm=None,
    )

    assert "contact_pressure_after_refusal" in result.violations
    assert "номер телефона" not in result.response.lower()
