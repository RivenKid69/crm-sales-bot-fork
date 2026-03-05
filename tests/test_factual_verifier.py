import pytest
from types import SimpleNamespace

from src.factual_verifier import FactualVerifier
from src.feature_flags import flags


class _StructuredLLM:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0
        self.prompts = []

    def generate_structured(self, prompt, schema, **kwargs):
        self.calls += 1
        self.prompts.append(prompt)
        if not self.outputs:
            raise RuntimeError("no scripted output")
        payload = self.outputs.pop(0)
        return schema.model_validate(payload)

    def generate(self, prompt: str):
        return "stub"


@pytest.fixture(autouse=True)
def _reset_flags():
    flags.clear_all_overrides()
    flags.set_override("response_factual_verifier", True)
    yield
    flags.clear_all_overrides()


def test_factual_verifier_pass_keeps_response():
    llm = _StructuredLLM([
        {
            "verdict": "pass",
            "checks": [{"claim": "Mini = 5 000 ₸/мес", "supported": True, "evidence_quote": "Mini 5 000 ₸/мес"}],
            "rewritten_response": "",
            "confidence": 0.9,
        }
    ])
    verifier = FactualVerifier(llm)
    result = verifier.verify_and_rewrite(
        user_message="Сколько стоит Mini?",
        candidate_response="Mini стоит 5 000 ₸/мес.",
        retrieved_facts="Mini — 5 000 ₸/мес.",
        intent="price_question",
        state="autonomous_discovery",
    )
    assert result.verifier_used is True
    assert result.verifier_verdict == "pass"
    assert result.changed is False
    assert result.final_response == "Mini стоит 5 000 ₸/мес."
    assert llm.calls == 1


def test_factual_verifier_fail_then_rewrite_pass():
    llm = _StructuredLLM([
        {
            "verdict": "fail",
            "checks": [{"claim": "Lite 120 000 ₸/год", "supported": False, "evidence_quote": ""}],
            "rewritten_response": "Lite стоит 150 000 ₸/год.",
            "confidence": 0.8,
        },
        {
            "verdict": "pass",
            "checks": [{"claim": "Lite 150 000 ₸/год", "supported": True, "evidence_quote": "Lite 150 000 ₸/год"}],
            "rewritten_response": "",
            "confidence": 0.85,
        },
    ])
    verifier = FactualVerifier(llm)
    result = verifier.verify_and_rewrite(
        user_message="Сколько стоит Lite?",
        candidate_response="Lite стоит 120 000 ₸/год.",
        retrieved_facts="Lite — 150 000 ₸/год.",
        intent="price_question",
        state="autonomous_discovery",
    )
    assert result.verifier_used is True
    assert result.verifier_verdict == "pass"
    assert result.changed is True
    assert result.final_response == "Lite стоит 150 000 ₸/год."
    assert "rewrite_pass" in result.reason_codes
    assert llm.calls == 2


def test_factual_verifier_fail_falls_back_to_safe_minimal_when_no_verified_rewrite():
    llm = _StructuredLLM([
        {
            "verdict": "fail",
            "checks": [{"claim": "Mini 120 000 ₸/мес", "supported": False, "evidence_quote": ""}],
            "rewritten_response": "",
            "confidence": 0.7,
        }
    ])
    verifier = FactualVerifier(llm)
    result = verifier.verify_and_rewrite(
        user_message="Сколько стоит Mini?",
        candidate_response="Mini стоит 120 000 ₸/мес.",
        retrieved_facts="Mini — 150 000 ₸/год.",
        intent="price_question",
        state="autonomous_discovery",
    )
    assert result.verifier_used is True
    assert result.verifier_verdict == "fail"
    assert result.fallback_required is False
    assert "недостаточно данных" in result.final_response.lower()
    assert "safe_minimal_fallback" in result.reason_codes
    assert "уточню у коллег" not in result.final_response.lower()


def test_factual_verifier_fail_never_returns_unverified_pass1_rewrite():
    llm = _StructuredLLM([
        {
            "verdict": "fail",
            "checks": [{"claim": "Mini 120 000 ₸/мес", "supported": False, "evidence_quote": ""}],
            "rewritten_response": "Mini стоит 1 ₸/мес.",
            "confidence": 0.71,
        },
        {
            "verdict": "fail",
            "checks": [{"claim": "Mini 1 ₸/мес", "supported": False, "evidence_quote": ""}],
            "rewritten_response": "",
            "confidence": 0.64,
        },
    ])
    verifier = FactualVerifier(llm)
    result = verifier.verify_and_rewrite(
        user_message="Сколько стоит Mini?",
        candidate_response="Mini стоит 120 000 ₸/мес.",
        retrieved_facts="Mini — 150 000 ₸/год.",
        intent="price_question",
        state="autonomous_discovery",
    )
    assert result.verifier_verdict == "fail"
    assert "safe_minimal_fallback" in result.reason_codes
    assert "pass1_rewrite_fallback" not in result.reason_codes
    assert "1 ₸/мес" not in result.final_response
    assert "недостаточно данных" in result.final_response.lower()


def test_factual_verifier_fail_returns_safe_minimal_contract():
    llm = _StructuredLLM([
        {
            "verdict": "fail",
            "checks": [{"claim": "Lite 120 000 ₸/год", "supported": False, "evidence_quote": ""}],
            "rewritten_response": "Lite стоит 120 000 ₸/год.",
            "confidence": 0.6,
        },
        {
            "verdict": "fail",
            "checks": [{"claim": "Lite 120 000 ₸/год", "supported": False, "evidence_quote": ""}],
            "rewritten_response": "",
            "confidence": 0.58,
        },
    ])
    verifier = FactualVerifier(llm)
    facts = "Lite — 150 000 ₸/год."
    result = verifier.verify_and_rewrite(
        user_message="Сколько стоит Lite?",
        candidate_response="Lite стоит 120 000 ₸/год.",
        retrieved_facts=facts,
        intent="price_question",
        state="autonomous_discovery",
    )
    assert result.verifier_verdict == "fail"
    assert "недостаточно данных" in result.final_response.lower()
    assert "safe_minimal_fallback" in result.reason_codes


def test_factual_verifier_prompt_includes_generic_completeness_contract():
    llm = _StructuredLLM([
        {
            "verdict": "pass",
            "checks": [{"claim": "варианты подключения", "supported": True, "evidence_quote": "Вариант A"}],
            "rewritten_response": "",
            "confidence": 0.93,
        }
    ])
    verifier = FactualVerifier(llm)
    verifier.verify_and_rewrite(
        user_message="Перечисли все варианты подключения.",
        candidate_response="Вариант A и вариант B.",
        retrieved_facts="Вариант A.\nВариант B.\nВариант C.",
        intent="integration_options",
        state="autonomous_discovery",
    )
    assert llm.prompts
    prompt_low = llm.prompts[0].lower()
    assert "критерий полноты" in prompt_low
    assert "все релевантные пункты из kb_context" in prompt_low
    assert "полный перечень тарифов" not in prompt_low
    assert llm.calls == 1


def test_factual_verifier_verify_only_keeps_model_pass_without_domain_override():
    llm = _StructuredLLM([
        {
            "verdict": "pass",
            "checks": [{"claim": "Mini 5 000 ₸/мес", "supported": True, "evidence_quote": "Mini 5 000 ₸/мес"}],
            "rewritten_response": "",
            "confidence": 0.92,
        }
    ])
    verifier = FactualVerifier(llm)
    result = verifier.verify_only(
        user_message="Назови все тарифы что у вас есть",
        candidate_response="Mini — 5 000 ₸/мес.",
        retrieved_facts="Mini — 5 000 ₸/мес.\nLite — 150 000 ₸/год.",
        intent="pricing_details",
        state="autonomous_discovery",
    )
    assert result is not None
    assert result.verdict == "pass"


def test_factual_verifier_db_only_prefers_matching_city_for_delivery_speed():
    llm = _StructuredLLM([
        {
            "verdict": "fail",
            "checks": [{"claim": "срок доставки", "supported": False, "evidence_quote": ""}],
            "rewritten_response": "",
            "confidence": 0.42,
        },
        {
            "verdict": "pass",
            "checks": [{"claim": "Доставка в Актау 3-5 рабочих дней", "supported": True, "evidence_quote": "Актау 3-5 рабочих дней"}],
            "rewritten_response": "",
            "confidence": 0.88,
        },
    ])
    llm.generate = lambda prompt: "Доставка в Актау занимает 3-5 рабочих дней."
    verifier = FactualVerifier(llm)
    result = verifier.verify_and_rewrite(
        user_message="Сколько дней занимает доставка в Актау?",
        candidate_response="Подскажите город.",
        retrieved_facts=(
            "[delivery/delivery_aktau]\n"
            "Доставка в Актау занимает 3-5 рабочих дней.\n"
            "=== КОНТЕКСТ ЭТАПА ===\n"
            "[delivery/delivery_shymkent]\n"
            "Доставка в Шымкент обычно занимает 1 день."
        ),
        intent="question_delivery_time",
        state="autonomous_discovery",
    )
    low = result.final_response.lower()
    assert "актау" in low
    assert ("3-5" in result.final_response) or ("3" in result.final_response and "5" in result.final_response)
    assert "шымкент" not in low
    assert "llm_kb_rewrite_pass" in result.reason_codes


def test_generator_post_process_rewrites_failed_response_with_llm_kb_rewrite(monkeypatch):
    from src.generator import ResponseGenerator

    class _FakeSection:
        def __init__(self):
            self.priority = 5
            self.facts = "Wipon overview."

    class _FakeRetriever:
        def __init__(self):
            self.kb = type("KB", (), {
                "sections": [_FakeSection()],
                "company_name": "Wipon",
                "company_description": "CRM",
            })()

    class _Flow:
        name = "autonomous"

        def get_template(self, _key: str):
            return None

    monkeypatch.setattr("src.generator.get_retriever", lambda: _FakeRetriever())
    flags.set_override("response_boundary_validator", False)
    flags.set_override("response_factual_verifier", True)
    flags.set_override("response_diversity", False)
    flags.set_override("apology_system", False)

    llm = _StructuredLLM([
        {
            "verdict": "fail",
            "checks": [{"claim": "Mini 120 000 ₸/мес", "supported": False, "evidence_quote": ""}],
            "rewritten_response": "",
            "confidence": 0.62,
        },
        {
            "verdict": "pass",
            "checks": [{"claim": "Mini 150 000 ₸/год", "supported": True, "evidence_quote": "Mini 150 000 ₸/год"}],
            "rewritten_response": "",
            "confidence": 0.9,
        },
    ])
    llm.generate = lambda prompt: "Mini стоит 150 000 ₸/год."
    generator = ResponseGenerator(llm=llm, flow=_Flow())
    processed, events = generator.post_process_only(
        response="Mini стоит 120 000 ₸/мес.",
        context={
            "intent": "price_question",
            "state": "autonomous_discovery",
            "user_message": "Сколько стоит Mini?",
            "history": [],
            "collected_data": {},
        },
        requested_action="answer_with_knowledge",
        selected_template_key="answer_with_knowledge",
        retrieved_facts="Mini — 150 000 ₸/год.",
    )
    assert "150 000" in processed
    assert "уточню у коллег" not in processed.lower()
    assert any(e.get("stage") == "factual_verifier" for e in events)


def test_generator_does_not_force_tis_quote_before_factual_verifier(monkeypatch):
    from src.generator import ResponseGenerator

    class _FakeSection:
        def __init__(self):
            self.priority = 5
            self.facts = "Wipon overview."

    class _FakeRetriever:
        def __init__(self):
            self.kb = type("KB", (), {
                "sections": [_FakeSection()],
                "company_name": "Wipon",
                "company_description": "CRM",
            })()

    class _Flow:
        name = "autonomous"

        def get_template(self, _key: str):
            return None

    monkeypatch.setattr("src.generator.get_retriever", lambda: _FakeRetriever())
    flags.set_override("response_boundary_validator", False)
    flags.set_override("response_factual_verifier", True)
    flags.set_override("response_diversity", False)
    flags.set_override("apology_system", False)
    flags.set_override("postprocess_semantic_mutations_after_verifier", True)
    flags.set_override("postprocess_override_enforce_enterprise_tis_quote", True)

    llm = _StructuredLLM([
        {
            "verdict": "pass",
            "checks": [{"claim": "TIS pricing", "supported": True, "evidence_quote": "220 000"}],
            "rewritten_response": "",
            "confidence": 0.93,
        }
    ])
    generator = ResponseGenerator(llm=llm, flow=_Flow())
    processed, events = generator.post_process_only(
        response="ТИС подходит для сети.",
        context={
            "intent": "pricing_details",
            "state": "autonomous_discovery",
            "user_message": "Сколько стоит ТИС?",
            "history": [{"user": "У нас 12 точек."}],
            "collected_data": {},
        },
        requested_action="autonomous_respond",
        selected_template_key="autonomous_respond",
        retrieved_facts="ТИС: 220 000 ₸/год за первую точку, +80 000 ₸ за каждую дополнительную.",
    )
    assert any(e.get("stage") == "factual_verifier" for e in events)
    assert llm.prompts
    prompt_low = llm.prompts[0].lower()
    assert "220 000" in prompt_low
    assert "80 000" in prompt_low
    assert "тариф тис" not in prompt_low
    assert processed == "ТИС подходит для сети."

    trace = generator._last_postprocess_meta.get("postprocess_trace", [])
    tis_trace = [entry for entry in trace if entry.get("rule_id") == "enforce_enterprise_tis_quote"]
    assert tis_trace
    assert tis_trace[-1].get("changed") is False
    assert tis_trace[-1].get("reason") == "migrated_to_llm_guardrails"


def test_post_verifier_semantic_mutation_triggers_verify_only_revert(monkeypatch):
    from src.generator import ResponseGenerator
    from src.response_boundary_validator import boundary_validator

    class _FakeSection:
        def __init__(self):
            self.priority = 5
            self.facts = "Wipon overview."

    class _FakeRetriever:
        def __init__(self):
            self.kb = type("KB", (), {
                "sections": [_FakeSection()],
                "company_name": "Wipon",
                "company_description": "CRM",
            })()

    class _Flow:
        name = "autonomous"

        def get_template(self, _key: str):
            return None

    monkeypatch.setattr("src.generator.get_retriever", lambda: _FakeRetriever())
    monkeypatch.setattr(
        boundary_validator,
        "validate_response",
        lambda response, context, llm: SimpleNamespace(
            response="Цена 1 руб.",
            violations=["ungrounded_capability"],
            fallback_used=True,
        ),
    )

    flags.set_override("response_boundary_validator", True)
    flags.set_override("response_factual_verifier", True)
    flags.set_override("response_diversity", False)
    flags.set_override("apology_system", False)

    llm = _StructuredLLM([
        {
            "verdict": "pass",
            "checks": [{"claim": "Mini 150 000", "supported": True, "evidence_quote": "150 000"}],
            "rewritten_response": "",
            "confidence": 0.9,
        },
        {
            "verdict": "fail",
            "checks": [{"claim": "1 руб", "supported": False, "evidence_quote": ""}],
            "rewritten_response": "",
            "confidence": 0.4,
        },
    ])
    generator = ResponseGenerator(llm=llm, flow=_Flow())
    original = "Mini стоит 150 000 ₸/год."
    processed, events = generator.post_process_only(
        response=original,
        context={
            "intent": "price_question",
            "state": "autonomous_discovery",
            "user_message": "Сколько стоит Mini?",
            "history": [],
            "collected_data": {},
        },
        requested_action="autonomous_respond",
        selected_template_key="autonomous_respond",
        retrieved_facts="Mini — 150 000 ₸/год.",
    )

    assert processed == original
    rechecks = [e for e in events if e.get("stage") == "factual_verify_only_recheck"]
    assert rechecks
    assert rechecks[-1].get("verdict") == "fail"
    pp_trace = generator._last_postprocess_meta.get("postprocess_trace", [])
    revert_steps = [x for x in pp_trace if x.get("rule_id") == "factual_verify_only_revert"]
    assert revert_steps
    assert revert_steps[-1].get("changed") is True


def test_factual_verifier_db_only_rewrite_skips_section_keys():
    llm = _StructuredLLM([
        {
            "verdict": "fail",
            "checks": [{"claim": "SLA 99.99%", "supported": False, "evidence_quote": ""}],
            "rewritten_response": "",
            "confidence": 0.55,
        }
    ])
    verifier = FactualVerifier(llm)
    result = verifier.verify_and_rewrite(
        user_message="Какие SLA и RTO/RPO?",
        candidate_response="SLA 99.99% и RTO 15 минут.",
        retrieved_facts="support/support_sla_enterprise_2004\n\n---\n\nSLA и RTO/RPO не указаны в предоставленных фактах.",
        intent="question_support",
        state="autonomous_discovery",
    )
    assert result.verifier_verdict == "fail"
    assert "support/support_sla_enterprise_2004" not in result.final_response


def test_generator_post_process_removes_colleague_fallback_without_facts(monkeypatch):
    from src.generator import ResponseGenerator

    class _FakeSection:
        def __init__(self):
            self.priority = 5
            self.facts = "Wipon overview."

    class _FakeRetriever:
        def __init__(self):
            self.kb = type("KB", (), {
                "sections": [_FakeSection()],
                "company_name": "Wipon",
                "company_description": "CRM",
            })()

    class _Flow:
        name = "autonomous"

        def get_template(self, _key: str):
            return None

    monkeypatch.setattr("src.generator.get_retriever", lambda: _FakeRetriever())
    flags.set_override("response_boundary_validator", False)
    flags.set_override("response_factual_verifier", True)
    flags.set_override("response_diversity", False)
    flags.set_override("apology_system", False)

    llm = _StructuredLLM([])
    generator = ResponseGenerator(llm=llm, flow=_Flow())
    processed, _ = generator.post_process_only(
        response="Уточню у коллег и вернусь с ответом.",
        context={
            "intent": "question_support",
            "state": "autonomous_discovery",
            "user_message": "Какие SLA?",
            "history": [],
            "collected_data": {},
        },
        requested_action="autonomous_respond",
        selected_template_key="autonomous_respond",
        retrieved_facts="",
    )
    assert "уточню у коллег" not in processed.lower()


def test_fact_disambiguation_stage_skips_factual_verifier(monkeypatch):
    from src.generator import ResponseGenerator

    class _FakeSection:
        def __init__(self):
            self.priority = 5
            self.facts = "Wipon overview."

    class _FakeRetriever:
        def __init__(self):
            self.kb = type("KB", (), {
                "sections": [_FakeSection()],
                "company_name": "Wipon",
                "company_description": "CRM",
            })()

    class _Flow:
        name = "autonomous"

        def get_template(self, _key: str):
            return None

    monkeypatch.setattr("src.generator.get_retriever", lambda: _FakeRetriever())
    flags.set_override("response_boundary_validator", False)
    flags.set_override("response_factual_verifier", True)
    flags.set_override("response_fact_disambiguation", True)
    flags.set_override("response_diversity", False)
    flags.set_override("apology_system", False)

    llm = _StructuredLLM([
        {
            "verdict": "pass",
            "checks": [{"claim": "stub", "supported": True, "evidence_quote": "stub"}],
            "rewritten_response": "",
            "confidence": 0.9,
        }
    ])
    generator = ResponseGenerator(llm=llm, flow=_Flow())
    processed, events = generator.post_process_only(
        response="Тариф Pro — хороший вариант.",
        context={
            "intent": "price_question",
            "state": "autonomous_discovery",
            "user_message": "Расскажите про pro",
            "history": [],
            "collected_data": {},
        },
        requested_action="autonomous_respond",
        selected_template_key="autonomous_respond",
        retrieved_facts=(
            "[pricing/pro_tariff]\nТариф Pro — 500 000 ₸/год.\n"
            "[equipment/pro_kit]\nКомплект PRO — оборудование для высокой нагрузки.\n"
            "[products/pro_ukm]\nWipon PRO УКМ — модуль маркировки и акцизной продукции.\n"
        ),
    )

    assert "Ответьте номером 1-3" in processed
    assert any(event.get("stage") == "fact_disambiguation" for event in events)
    assert all(event.get("stage") != "factual_verifier" for event in events)
    assert llm.calls == 0


def test_db_only_response_prefers_price_sentence_for_price_question():
    verifier = FactualVerifier(llm=SimpleNamespace())
    facts = (
        "Подключение ТИС занимает 1-2 дня при готовых документах.\n"
        "Стоимость подключения ТИС: 220 000 ₸/год за первую точку и +80 000 ₸/год за каждую дополнительную."
    )
    response = verifier._build_db_only_response(
        user_message="Сколько стоит подключение ТИС?",
        retrieved_facts=facts,
    )
    assert "220 000" in response
    assert "₸" in response


def test_db_only_response_prefers_catalog_sentence_for_ecosystem_question():
    verifier = FactualVerifier(llm=SimpleNamespace())
    facts = (
        "Wipon — решение для розничного бизнеса в Казахстане.\n"
        "Экосистема Wipon включает продукты Kassa, Desktop и ТИС.\n"
        "Есть тарифы для разных масштабов бизнеса."
    )
    response = verifier._build_db_only_response(
        user_message="Какие продукты есть в экосистеме Wipon?",
        retrieved_facts=facts,
    )
    low = response.lower()
    assert "kassa" in low
    assert "desktop" in low
    assert "тис" in low


def test_db_only_response_for_ukm_price_keeps_ukm_and_price():
    verifier = FactualVerifier(llm=SimpleNamespace())
    facts = (
        "Wipon PRO УКМ — программный модуль для акцизной продукции.\n"
        "Цена: 12 000 ₸/год.\n"
        "Тариф Pro — 500 000 ₸/год для сетей."
    )
    response = verifier._build_db_only_response(
        user_message="Что такое Wipon PRO УКМ и сколько стоит?",
        retrieved_facts=facts,
    )
    low = response.lower()
    assert "укм" in low
    assert "акциз" in low
    assert "12 000" in response


def test_db_only_response_for_pro_kit_keeps_kit_price_and_components():
    verifier = FactualVerifier(llm=SimpleNamespace())
    facts = (
        "Тариф Pro — 500 000 ₸/год.\n"
        "Комплект PRO — 360 000 ₸ (единоразово).\n"
        "Состав: POS DUO, сканер, принтер и денежный ящик."
    )
    response = verifier._build_db_only_response(
        user_message="Что входит в комплект PRO оборудования и сколько он стоит?",
        retrieved_facts=facts,
    )
    low = response.lower()
    assert "360 000" in response
    assert "pos duo" in low
    assert "сканер" in low
    assert "принтер" in low
    assert "ящик" in low


def test_db_only_response_for_tariff_overview_keeps_all_core_tariffs():
    verifier = FactualVerifier(llm=SimpleNamespace())
    response = verifier._build_db_only_response(
        user_message="Какие тарифы есть у Wipon и сколько они стоят?",
        retrieved_facts=(
            "Тариф Mini — 5 000 ₸/мес.\n"
            "Тариф Lite — 150 000 ₸/год.\n"
            "Тариф Standard — 220 000 ₸/год.\n"
            "Тариф Pro — 500 000 ₸/год."
        ),
    )
    assert "Mini" in response
    assert "5 000" in response
    assert "Lite" in response
    assert "150 000" in response
    assert "Standard" in response
    assert "220 000" in response
    assert "Pro" in response
    assert "500 000" in response


def test_db_only_response_for_printer_compare_is_facts_driven():
    verifier = FactualVerifier(llm=SimpleNamespace())
    response = verifier._build_db_only_response(
        user_message="Какие принтеры чеков у вас есть? Чем они отличаются?",
        retrieved_facts=(
            "GP-C58 — чековый принтер 58 мм.\n"
            "GP-C200I — чековый принтер 80 мм с автоотрезом.\n"
            "Оба поддерживают печать чеков в Wipon."
        ),
    )
    low = response.lower()
    assert "gp-c58" in low
    assert "58 мм" in low
    assert "gp-c200i" in low
    assert "80 мм" in low


def test_db_only_response_for_triple_quadro_compare_is_facts_driven():
    verifier = FactualVerifier(llm=SimpleNamespace())
    response = verifier._build_db_only_response(
        user_message="Чем отличается Wipon Triple от Wipon Quadro?",
        retrieved_facts=(
            "Wipon Triple стоит 330 000 ₸.\n"
            "Wipon Quadro стоит 365 000 ₸.\n"
            "У Quadro есть экран покупателя, у Triple его нет."
        ),
    )
    assert "Triple" in response
    assert "330 000" in response
    assert "Quadro" in response
    assert "365 000" in response


def test_db_only_response_does_not_invent_printer_compare_without_facts():
    verifier = FactualVerifier(llm=SimpleNamespace())
    response = verifier._build_db_only_response(
        user_message="Какие принтеры чеков у вас есть? Чем они отличаются?",
        retrieved_facts="Доступна только общая информация без моделей.",
    )
    low = response.lower()
    assert "gp-c58" not in low
    assert "gp-c200i" not in low


def test_generator_runs_factual_verifier_for_direct_factual_descriptive_answer(monkeypatch):
    from src.generator import ResponseGenerator

    class _FakeSection:
        def __init__(self):
            self.priority = 5
            self.facts = "Wipon overview."

    class _FakeRetriever:
        def __init__(self):
            self.kb = type("KB", (), {
                "sections": [_FakeSection()],
                "company_name": "Wipon",
                "company_description": "CRM",
            })()

    class _Flow:
        name = "autonomous"

        def get_template(self, _key: str):
            return None

    monkeypatch.setattr("src.generator.get_retriever", lambda: _FakeRetriever())
    flags.set_override("response_boundary_validator", False)
    flags.set_override("response_factual_verifier", True)
    flags.set_override("response_diversity", False)
    flags.set_override("apology_system", False)

    llm = _StructuredLLM([
        {
            "verdict": "pass",
            "checks": [{"claim": "stub", "supported": True, "evidence_quote": "stub"}],
            "rewritten_response": "",
            "confidence": 0.9,
        }
    ])
    generator = ResponseGenerator(llm=llm, flow=_Flow())
    processed, events = generator.post_process_only(
        response="Wipon Desktop — программа учёта для Windows.",
        context={
            "intent": "question_wipon_desktop",
            "state": "autonomous_discovery",
            "user_message": "Что такое Wipon Desktop?",
            "history": [],
            "collected_data": {},
        },
        requested_action="autonomous_respond",
        selected_template_key="autonomous_respond",
        retrieved_facts="Wipon Desktop — программа учёта товаров и продаж для Windows ПК.",
    )

    assert processed
    assert any(event.get("stage") == "factual_verifier" for event in events)
    assert llm.calls == 1


def test_generator_skips_factual_verifier_when_facts_do_not_cover_kit_pricing(monkeypatch):
    from src.generator import ResponseGenerator

    class _FakeSection:
        def __init__(self):
            self.priority = 5
            self.facts = "Wipon overview."

    class _FakeRetriever:
        def __init__(self):
            self.kb = type("KB", (), {
                "sections": [_FakeSection()],
                "company_name": "Wipon",
                "company_description": "CRM",
            })()

    class _Flow:
        name = "autonomous"

        def get_template(self, _key: str):
            return None

    monkeypatch.setattr("src.generator.get_retriever", lambda: _FakeRetriever())
    flags.set_override("response_boundary_validator", False)
    flags.set_override("response_factual_verifier", True)
    flags.set_override("response_diversity", False)
    flags.set_override("apology_system", False)

    llm = _StructuredLLM([
        {
            "verdict": "pass",
            "checks": [{"claim": "stub", "supported": True, "evidence_quote": "stub"}],
            "rewritten_response": "",
            "confidence": 0.9,
        }
    ])
    generator = ResponseGenerator(llm=llm, flow=_Flow())
    processed, events = generator.post_process_only(
        response=(
            "Комплект PRO стоит 360 000 ₸ и включает POS DUO, сканер, принтер и ящик."
        ),
        context={
            "intent": "question_equipment_general",
            "state": "autonomous_discovery",
            "user_message": "Что входит в комплект PRO оборудования и сколько он стоит?",
            "history": [],
            "collected_data": {},
        },
        requested_action="autonomous_respond",
        selected_template_key="autonomous_respond",
        retrieved_facts="Тариф Pro — 500 000 ₸/год для сети до 5 точек.",
    )

    assert processed
    assert all(event.get("stage") != "factual_verifier" for event in events)
    assert llm.calls == 0
