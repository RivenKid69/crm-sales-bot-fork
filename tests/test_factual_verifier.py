import pytest

from src.factual_verifier import FactualVerifier
from src.feature_flags import flags


class _StructuredLLM:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0

    def generate_structured(self, prompt, schema, **kwargs):
        self.calls += 1
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


def test_factual_verifier_fail_rewrites_to_db_only():
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
    assert "150 000" in result.final_response
    assert "уточню у коллег" not in result.final_response.lower()


def test_generator_post_process_rewrites_failed_response_to_db_only(monkeypatch):
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
        }
    ])
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
