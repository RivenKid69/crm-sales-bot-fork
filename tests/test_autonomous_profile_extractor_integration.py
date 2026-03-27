from src.autonomous_profile_extractor import AutonomousProfileSnapshot
from src.bot import SalesBot
from src.cta_generator import CTAResult


class _SnapshotLLM:
    model = "snapshot-mock"

    def __init__(self, snapshot=None, structured_error=None):
        self.snapshot = snapshot
        self.structured_error = structured_error
        self.prompts = []

    def generate(self, prompt, **kwargs):
        return "Ответ"

    def generate_structured(self, prompt, schema, **kwargs):
        self.prompts.append(prompt)
        if self.structured_error is not None:
            raise self.structured_error
        return self.snapshot


class _FakeDecision:
    def __init__(self, sm_result):
        self._sm_result = sm_result

    def to_sm_result(self):
        return self._sm_result


def _mock_classification(extracted_data=None):
    return {
        "intent": "question_features",
        "extracted_data": extracted_data or {},
        "confidence": 0.92,
        "method": "mock",
        "style_modifiers": [],
        "secondary_signals": [],
        "semantic_frame": {},
        "style_separation_applied": False,
    }


def _mock_tone():
    return {
        "tone": "neutral",
        "frustration_level": 0,
        "tone_instruction": "",
        "style_instruction": "",
        "should_apologize": False,
        "should_offer_exit": False,
    }


def _sm_result():
    return {
        "action": "autonomous_respond",
        "next_state": "greeting",
        "prev_state": "greeting",
        "goal": "",
        "collected_data": {},
        "missing_data": [],
        "spin_phase": None,
        "optional_data": [],
        "terminal_state_requirements": {},
        "resolution_trace": {"winning_action_metadata": {}},
        "reason_codes": [],
        "is_final": False,
    }


def _disable_generation_side_effects(monkeypatch, bot):
    monkeypatch.setattr(bot, "_analyze_tone", lambda *_args, **_kwargs: _mock_tone())
    monkeypatch.setattr(bot.generator, "prepare_response_context", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(bot.generator, "_get_template", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(bot.generator, "generate", lambda *_args, **_kwargs: "Ответ")
    monkeypatch.setattr(
        bot,
        "_apply_cta",
        lambda response, *_args, **_kwargs: CTAResult(
            original_response=response,
            cta=None,
            final_response=response,
            cta_added=False,
            skip_reason="test",
        ),
    )


def test_process_injects_autonomous_profile_snapshot_before_orchestrator(monkeypatch):
    llm = _SnapshotLLM(
        snapshot={
            "contact_name": "Айдар",
            "business_type": "кофейня",
            "city": "Жезказган",
            "automation_before": True,
        }
    )
    bot = SalesBot(llm=llm, flow_name="autonomous")
    _disable_generation_side_effects(monkeypatch, bot)

    bot.transcript.append_turn_internal(
        user_text="Здравствуйте",
        bot_text="Добрый день. Чем занимаетесь?",
        intent="greeting",
        state="greeting",
        action="greet_back",
    )

    monkeypatch.setattr(
        bot.classifier,
        "classify",
        lambda *_args, **_kwargs: _mock_classification(
            {
                "client_name": "Старое имя",
                "business_type": "старое значение",
            }
        ),
    )

    captured = {}

    def _process_turn(**kwargs):
        captured["extracted_data"] = kwargs["extracted_data"]
        return _FakeDecision(_sm_result())

    monkeypatch.setattr(bot._orchestrator, "process_turn", _process_turn)

    bot.process("Меня зовут Айдар, у нас кофейня в Жезказгане, сейчас UMAG стоит")

    assert captured["extracted_data"] == {
        "contact_name": "Айдар",
        "business_type": "кофейня",
        "city": "Жезказган",
        "automation_before": True,
    }
    assert "client_name" not in captured["extracted_data"]
    assert "Здравствуйте" in llm.prompts[0]
    assert "Меня зовут Айдар, у нас кофейня в Жезказгане, сейчас UMAG стоит" in llm.prompts[0]


def test_partial_snapshot_does_not_clear_existing_collected_values(monkeypatch):
    bot = SalesBot(llm=_SnapshotLLM(), flow_name="autonomous")
    bot.state_machine.collected_data["contact_name"] = "Айдар"
    bot.state_machine.collected_data["city"] = "Жезказган"

    monkeypatch.setattr(
        bot.autonomous_profile_extractor,
        "extract",
        lambda *_args, **_kwargs: AutonomousProfileSnapshot(automation_before=True),
    )

    merged = bot._apply_autonomous_profile_snapshot(
        {},
        current_state="greeting",
        user_message="У нас сейчас UMAG стоит",
    )
    bot.state_machine.update_data(merged)

    assert bot.state_machine.collected_data["contact_name"] == "Айдар"
    assert bot.state_machine.collected_data["city"] == "Жезказган"
    assert bot.state_machine.collected_data["automation_before"] is True
    assert "client_name" not in merged


def test_snapshot_failure_keeps_original_extracted_data(monkeypatch):
    llm = _SnapshotLLM(structured_error=RuntimeError("timeout"))
    bot = SalesBot(llm=llm, flow_name="autonomous")
    _disable_generation_side_effects(monkeypatch, bot)

    original_extracted = {
        "client_name": "Иван",
        "business_type": "магазин",
    }
    monkeypatch.setattr(
        bot.classifier,
        "classify",
        lambda *_args, **_kwargs: _mock_classification(original_extracted),
    )

    captured = {}

    def _process_turn(**kwargs):
        captured["extracted_data"] = kwargs["extracted_data"]
        return _FakeDecision(_sm_result())

    monkeypatch.setattr(bot._orchestrator, "process_turn", _process_turn)

    bot.process("У нас магазин")

    assert captured["extracted_data"] == original_extracted


def test_non_autonomous_flow_skips_profile_snapshot():
    llm = _SnapshotLLM(
        snapshot={"contact_name": "Айдар", "business_type": "кофейня"}
    )
    bot = SalesBot(llm=llm, flow_name="bant")

    result = bot._apply_autonomous_profile_snapshot(
        {"client_name": "Иван", "business_type": "магазин"},
        current_state="greeting",
        user_message="Меня зовут Айдар",
    )

    assert result == {"client_name": "Иван", "business_type": "магазин"}
    assert llm.prompts == []
