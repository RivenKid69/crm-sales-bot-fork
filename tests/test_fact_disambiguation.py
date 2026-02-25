from src.feature_flags import flags
from src.knowledge.fact_disambiguation import detect_fact_disambiguation


def _build_facts(query_sections, state_sections=None):
    parts = []
    for key, fact in query_sections:
        parts.append(f"[{key}]\n{fact}\n")
    query_text = "".join(parts)
    if not state_sections:
        return query_text

    state_parts = []
    for key, fact in state_sections:
        state_parts.append(f"[{key}]\n{fact}\n")
    return f"{query_text}\n=== КОНТЕКСТ ЭТАПА ===\n{''.join(state_parts)}"


def setup_function():
    flags.clear_all_overrides()
    flags.set_override("response_fact_disambiguation", True)


def teardown_function():
    flags.clear_all_overrides()


def test_ambiguous_pro_requires_clarification():
    facts = _build_facts(
        query_sections=[
            ("pricing/pro_tariff", "Тариф Pro — 500 000 ₸/год, для сети магазинов."),
            ("equipment/pro_kit", "Комплект PRO — кассовое оборудование для высокой нагрузки."),
            ("products/pro_ukm", "Wipon PRO УКМ — модуль маркировки и акцизной продукции."),
        ]
    )
    decision = detect_fact_disambiguation(
        user_message="Расскажите про Pro",
        retrieved_facts=facts,
        history=[],
    )
    assert decision.should_disambiguate is True
    assert "Ответьте номером 1-3" in decision.clarification_text
    assert len(decision.options) >= 2
    assert any("Тариф Pro" in option for option in decision.options)


def test_specific_tariff_pro_does_not_clarify():
    facts = _build_facts(
        query_sections=[
            ("pricing/pro_tariff", "Тариф Pro — 500 000 ₸/год, для сети магазинов."),
            ("equipment/pro_kit", "Комплект PRO — кассовое оборудование для высокой нагрузки."),
            ("products/pro_ukm", "Wipon PRO УКМ — модуль маркировки и акцизной продукции."),
        ]
    )
    decision = detect_fact_disambiguation(
        user_message="Сколько стоит тариф Pro?",
        retrieved_facts=facts,
        history=[],
    )
    assert decision.should_disambiguate is False
    assert "message_specific_tariff" in decision.reason_codes


def test_price_only_pro_stays_ambiguous_and_requests_clarification():
    facts = _build_facts(
        query_sections=[
            ("pricing/pro_tariff", "Тариф Pro — 500 000 ₸/год, для сети магазинов."),
            ("equipment/pro_kit", "Комплект PRO — кассовое оборудование для высокой нагрузки."),
            ("products/pro_ukm", "Wipon PRO УКМ — модуль маркировки и акцизной продукции."),
        ]
    )
    decision = detect_fact_disambiguation(
        user_message="Сколько стоит Pro?",
        retrieved_facts=facts,
        history=[],
    )
    assert decision.should_disambiguate is True
    assert "Ответьте номером 1-3" in decision.clarification_text


def test_dedup_same_type_does_not_trigger_false_positive():
    facts = _build_facts(
        query_sections=[
            ("pricing/pro_tariff_1", "Тариф Pro — 500 000 ₸/год."),
            ("pricing/pro_tariff_2", "Тариф Wipon Pro — 500 000 ₸/год и расширенные отчёты."),
            ("pricing/pro_tariff_3", "Тариф Pro — для 5 точек и нескольких складов."),
            ("pricing/standard_tariff", "Тариф Standard — 220 000 ₸/год."),
        ]
    )
    decision = detect_fact_disambiguation(
        user_message="Расскажите про Pro",
        retrieved_facts=facts,
        history=[],
    )
    assert decision.should_disambiguate is False
    assert "no_family_type_conflict" in decision.reason_codes


def test_clarification_repeat_limit_fail_open():
    facts = _build_facts(
        query_sections=[
            ("pricing/pro_tariff", "Тариф Pro — 500 000 ₸/год, для сети магазинов."),
            ("equipment/pro_kit", "Комплект PRO — кассовое оборудование для высокой нагрузки."),
        ]
    )
    history = [
        {
            "user": "Расскажите про Pro",
            "bot": "Уточните, пожалуйста, что вы имеете в виду под «Pro»:\n"
            "1) Тариф Pro\n2) Комплект Pro\nОтветьте номером 1-3 или напишите вариант словами.",
        },
        {
            "user": "Не понял",
            "bot": "Уточните, пожалуйста, что вы имеете в виду под «Pro»:\n"
            "1) Тариф Pro\n2) Комплект Pro\nОтветьте номером 1-3 или напишите вариант словами.",
        },
    ]
    decision = detect_fact_disambiguation(
        user_message="ещё раз про pro",
        retrieved_facts=facts,
        history=history,
    )
    assert decision.should_disambiguate is False
    assert "clarification_repeat_limit" in decision.reason_codes


def test_single_section_not_confuse_block_triggers_clarification():
    facts = _build_facts(
        query_sections=[
            (
                "products/wipon_pro",
                "Wipon PRO УКМ — модуль для маркировки.\n"
                "⚠️ НЕ ПУТАТЬ: «Тариф Pro» (500 000 ₸/год) — программа, "
                "«Комплект PRO» (360 000 ₸ разово) — оборудование.",
            )
        ],
    )
    decision = detect_fact_disambiguation(
        user_message="Что такое Pro?",
        retrieved_facts=facts,
        history=[],
    )
    assert decision.should_disambiguate is True
    assert len(decision.options) >= 2


def test_state_backfill_is_ignored_for_ambiguity():
    facts = _build_facts(
        query_sections=[
            ("pricing/pro_tariff", "Тариф Pro — 500 000 ₸/год."),
        ],
        state_sections=[
            ("equipment/pro_kit", "Комплект PRO — кассовое оборудование."),
            ("products/pro_ukm", "Wipon PRO УКМ — модуль маркировки."),
        ],
    )
    decision = detect_fact_disambiguation(
        user_message="Расскажите про Pro",
        retrieved_facts=facts,
        history=[],
    )
    assert decision.should_disambiguate is False
    assert "no_family_type_conflict" in decision.reason_codes
