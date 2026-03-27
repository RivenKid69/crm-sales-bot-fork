from src.autonomous_profile_extractor import (
    AutonomousProfileExtractor,
    AutonomousProfileSnapshot,
)


class _StructuredLLM:
    model = "structured-mock"

    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.prompts = []
        self.kwargs = []

    def generate_structured(self, prompt, schema, **kwargs):
        self.prompts.append(prompt)
        self.kwargs.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.payload


def test_extract_builds_snapshot_from_full_history():
    llm = _StructuredLLM(
        payload={
            "contact_name": "Айдар",
            "business_type": "кофейня",
            "city": "Жезказган",
            "automation_before": True,
        }
    )
    extractor = AutonomousProfileExtractor(llm)

    result = extractor.extract(
        [
            {"user": "Меня зовут Айдар", "bot": "Приятно познакомиться."},
            {"user": "У нас кофейня", "bot": "В каком вы городе?"},
            {"user": "Мы в Жезказгане, сейчас UMAG стоит", "bot": ""},
        ]
    )

    assert result == AutonomousProfileSnapshot(
        contact_name="Айдар",
        business_type="кофейня",
        city="Жезказган",
        automation_before=True,
    )
    assert "Меня зовут Айдар" in llm.prompts[0]
    assert "У нас кофейня" in llm.prompts[0]
    assert "Мы в Жезказгане, сейчас UMAG стоит" in llm.prompts[0]
    assert llm.kwargs[0]["purpose"] == "autonomous_profile_snapshot"
    assert llm.kwargs[0]["temperature"] == 0.0


def test_prompt_keeps_bot_lines_only_as_context():
    llm = _StructuredLLM(payload=None)
    extractor = AutonomousProfileExtractor(llm)

    extractor.extract(
        [
            {"user": "Здравствуйте", "bot": "Вы в Караганде и у вас ресторан?"},
            {"user": "Пока просто смотрю", "bot": ""},
        ]
    )

    prompt = llm.prompts[0]
    assert "Вы в Караганде и у вас ресторан?" in prompt
    assert "Используй только строки с префиксом 'Клиент:' как доказательство." in prompt
    assert "Строки с префиксом 'Вы:'" in prompt


def test_extract_returns_none_on_llm_failure():
    extractor = AutonomousProfileExtractor(
        _StructuredLLM(error=RuntimeError("boom"))
    )

    result = extractor.extract([{"user": "Привет", "bot": ""}])

    assert result is None
