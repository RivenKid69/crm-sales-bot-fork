from src.feature_flags import flags
from src.generator import ResponseGenerator


class _FakeSection:
    def __init__(self, facts: str = "Wipon overview.", priority: int = 5):
        self.priority = priority
        self.facts = facts


class _FakeRetriever:
    def __init__(self):
        self.kb = type("KB", (), {
            "sections": [_FakeSection()],
            "company_name": "Wipon",
            "company_description": "CRM",
        })()


class _FlowAutonomous:
    name = "autonomous"

    def get_template(self, _key: str):
        return None


class _FlowNonAutonomous:
    name = "spin_selling"

    def get_template(self, _key: str):
        return None


class _NoopLLM:
    def generate(self, prompt: str, **kwargs):
        return "stub"


def setup_function():
    flags.clear_all_overrides()


def teardown_function():
    flags.clear_all_overrides()


def _ambiguous_pro_facts() -> str:
    return (
        "[pricing/pro_tariff]\nТариф Pro — 500 000 ₸/год для сети.\n"
        "[equipment/pro_kit]\nКомплект PRO — кассовое оборудование для высокой нагрузки.\n"
        "[products/pro_ukm]\nWipon PRO УКМ — модуль маркировки и акцизной продукции.\n"
    )


def test_autonomous_ambiguous_turn_triggers_fact_disambiguation(monkeypatch):
    monkeypatch.setattr("src.generator.get_retriever", lambda: _FakeRetriever())
    flags.set_override("response_fact_disambiguation", True)
    flags.set_override("response_factual_verifier", False)
    flags.set_override("response_boundary_validator", False)
    flags.set_override("response_diversity", False)
    flags.set_override("apology_system", False)

    generator = ResponseGenerator(llm=_NoopLLM(), flow=_FlowAutonomous())
    processed, events = generator.post_process_only(
        response="Тариф Pro — максимальный тариф.",
        context={
            "intent": "price_question",
            "state": "autonomous_discovery",
            "user_message": "Расскажите про Pro",
            "history": [],
            "collected_data": {},
        },
        requested_action="autonomous_respond",
        selected_template_key="autonomous_respond",
        retrieved_facts=_ambiguous_pro_facts(),
    )

    assert "Ответьте номером 1-3" in processed
    assert "1)" in processed and "2)" in processed
    assert any(event.get("stage") == "fact_disambiguation" for event in events)


def test_autonomous_specific_turn_does_not_trigger_fact_disambiguation(monkeypatch):
    monkeypatch.setattr("src.generator.get_retriever", lambda: _FakeRetriever())
    flags.set_override("response_fact_disambiguation", True)
    flags.set_override("response_factual_verifier", False)
    flags.set_override("response_boundary_validator", False)
    flags.set_override("response_diversity", False)
    flags.set_override("apology_system", False)

    generator = ResponseGenerator(llm=_NoopLLM(), flow=_FlowAutonomous())
    processed, events = generator.post_process_only(
        response="Тариф Pro стоит 500 000 ₸/год.",
        context={
            "intent": "price_question",
            "state": "autonomous_discovery",
            "user_message": "Сколько стоит тариф Pro?",
            "history": [],
            "collected_data": {},
        },
        requested_action="autonomous_respond",
        selected_template_key="autonomous_respond",
        retrieved_facts=_ambiguous_pro_facts(),
    )

    assert "Ответьте номером 1-3" not in processed
    assert all(event.get("stage") != "fact_disambiguation" for event in events)


def test_non_autonomous_turn_is_unchanged(monkeypatch):
    monkeypatch.setattr("src.generator.get_retriever", lambda: _FakeRetriever())
    flags.set_override("response_fact_disambiguation", True)
    flags.set_override("response_factual_verifier", False)
    flags.set_override("response_boundary_validator", False)
    flags.set_override("response_diversity", False)
    flags.set_override("apology_system", False)

    generator = ResponseGenerator(llm=_NoopLLM(), flow=_FlowNonAutonomous())
    processed, events = generator.post_process_only(
        response="Тариф Pro — это максимальный тариф.",
        context={
            "intent": "price_question",
            "state": "discovery",
            "user_message": "Расскажите про Pro",
            "history": [],
            "collected_data": {},
        },
        requested_action="answer_with_facts",
        selected_template_key="answer_with_facts",
        retrieved_facts=_ambiguous_pro_facts(),
    )

    assert "Ответьте номером 1-3" not in processed
    assert all(event.get("stage") != "fact_disambiguation" for event in events)
