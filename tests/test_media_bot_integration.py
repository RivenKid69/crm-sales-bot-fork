from src.bot import SalesBot
from src.media_turn_context import MediaTurnContext


class _MediaBotLLM:
    model = "media-bot-mock"

    def generate(self, prompt, **kwargs):
        return "Ответ"


class _FakeDecision:
    def __init__(self, sm_result):
        self._sm_result = sm_result

    def to_sm_result(self):
        return self._sm_result


def _mock_classification():
    return {
        "intent": "question_features",
        "extracted_data": {},
        "confidence": 0.91,
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


def _prepared_response_context(kb_facts: str = "KB FACT"):
    return {
        "retrieved_facts": kb_facts,
        "kb_retrieved_facts": kb_facts,
        "retrieved_urls": "",
        "fact_keys": ["kb-1"],
        "grounding_contract_version": 2,
    }


def _sm_result(*, action="autonomous_respond", winning_action_metadata=None):
    return {
        "action": action,
        "next_state": "greeting",
        "prev_state": "greeting",
        "goal": "",
        "collected_data": {"company_name": "Wipon"},
        "missing_data": [],
        "spin_phase": None,
        "optional_data": [],
        "terminal_state_requirements": {},
        "resolution_trace": {
            "winning_action_metadata": winning_action_metadata or {},
        },
        "reason_codes": [],
        "is_final": False,
    }


def test_autonomous_media_turn_goes_through_orchestrator(monkeypatch):
    bot = SalesBot(llm=_MediaBotLLM(), flow_name="autonomous")

    monkeypatch.setattr(bot.classifier, "classify", lambda *_args, **_kwargs: _mock_classification())
    monkeypatch.setattr(bot, "_analyze_tone", lambda *_args, **_kwargs: _mock_tone())
    monkeypatch.setattr(
        bot.generator,
        "prepare_response_context",
        lambda *_args, **_kwargs: _prepared_response_context("KB FACT"),
    )

    captured = {}

    def _process_turn(**kwargs):
        captured["media_turn_context"] = kwargs["media_turn_context"]
        return _FakeDecision(
            _sm_result(
                winning_action_metadata={
                    "response_mode": "media_only",
                    "selected_media_card_ids": ["card-1"],
                    "route_reasoning": "selected current attachment",
                    "route_source": "llm",
                }
            )
        )

    monkeypatch.setattr(bot._orchestrator, "process_turn", _process_turn)

    generated = {}

    def _generate(_action, context):
        generated["context"] = context
        return "Ответ по media"

    monkeypatch.setattr(bot.generator, "generate", _generate)

    bot.set_pending_media_meta(
        {
            "source_user_text": "что в документе?",
            "source_session_id": "sess-1",
            "source_user_id": "user-1",
            "knowledge_cards": [
                {
                    "knowledge_id": "card-1",
                    "attachment_fingerprint": "fp-1",
                    "file_name": "doc.pdf",
                    "media_kind": "document",
                    "summary": "Это документ компании Альфа Логистик.",
                    "facts": ["Компания Альфа Логистик."],
                    "extracted_data": {"company_name": "Альфа Логистик"},
                    "answer_context": "Это документ компании Альфа Логистик.",
                }
            ],
            "media_facts": ["Компания Альфа Логистик."],
            "extracted_data": {"company_name": "Альфа Логистик"},
        }
    )

    result = bot.process("что в документе?\n\nДополнительный контекст из вложений клиента: ...")

    assert captured["media_turn_context"] is not None
    assert [card["knowledge_id"] for card in captured["media_turn_context"].current_cards] == ["card-1"]
    expected_media_grounding = bot._build_media_context_from_cards(
        [
            {
                "knowledge_id": "card-1",
                "attachment_fingerprint": "fp-1",
                "file_name": "doc.pdf",
                "media_kind": "document",
                "summary": "Это документ компании Альфа Логистик.",
                "facts": ["Компания Альфа Логистик."],
                "extracted_data": {"company_name": "Альфа Логистик"},
                "answer_context": "Это документ компании Альфа Логистик.",
            }
        ]
    )
    assert generated["context"]["media_route_mode"] == "media_only"
    assert generated["context"]["selected_media_grounding"] == expected_media_grounding
    assert generated["context"]["kb_retrieved_facts"] == "KB FACT"
    assert generated["context"]["final_grounding_facts"] == generated["context"]["retrieved_facts"]
    assert "KB FACT" not in generated["context"]["retrieved_facts"]
    assert "Компания Альфа Логистик." in generated["context"]["retrieved_facts"]
    assert result["state"] == "greeting"


def test_historical_media_followup_uses_winning_action_metadata(monkeypatch):
    bot = SalesBot(llm=_MediaBotLLM(), flow_name="autonomous")

    bot.context_window.episodic_memory.upsert_media_knowledge_cards(
        [
            {
                "knowledge_id": "card-1",
                "attachment_fingerprint": "fp-1",
                "file_name": "doc.pdf",
                "media_kind": "document",
                "summary": "Это документ компании Альфа Логистик.",
                "facts": ["Компания Альфа Логистик."],
                "extracted_data": {"company_name": "Альфа Логистик"},
                "answer_context": "Это документ компании Альфа Логистик.",
            }
        ]
    )

    monkeypatch.setattr(bot.classifier, "classify", lambda *_args, **_kwargs: _mock_classification())
    monkeypatch.setattr(bot, "_analyze_tone", lambda *_args, **_kwargs: _mock_tone())
    monkeypatch.setattr(
        bot.generator,
        "prepare_response_context",
        lambda *_args, **_kwargs: _prepared_response_context("KB FACT"),
    )
    monkeypatch.setattr(
        bot._orchestrator,
        "process_turn",
        lambda **_kwargs: _FakeDecision(
            _sm_result(
                winning_action_metadata={
                    "response_mode": "media_only",
                    "selected_media_card_ids": ["card-1"],
                    "route_reasoning": "historical follow-up",
                    "route_source": "llm",
                }
            )
        ),
    )

    generated = {}

    def _generate(_action, context):
        generated["context"] = context
        return "Ответ"

    monkeypatch.setattr(bot.generator, "generate", _generate)

    bot.process("что там в документе?")

    assert generated["context"]["media_route_mode"] == "media_only"
    assert generated["context"]["final_grounding_facts"] == generated["context"]["retrieved_facts"]
    assert "KB FACT" not in generated["context"]["retrieved_facts"]
    assert "Компания Альфа Логистик." in generated["context"]["retrieved_facts"]


def test_hybrid_media_route_keeps_kb_and_selected_media_separate(monkeypatch):
    bot = SalesBot(llm=_MediaBotLLM(), flow_name="autonomous")

    monkeypatch.setattr(bot.classifier, "classify", lambda *_args, **_kwargs: _mock_classification())
    monkeypatch.setattr(bot, "_analyze_tone", lambda *_args, **_kwargs: _mock_tone())
    monkeypatch.setattr(
        bot.generator,
        "prepare_response_context",
        lambda *_args, **_kwargs: _prepared_response_context("KB FACT"),
    )
    monkeypatch.setattr(
        bot._orchestrator,
        "process_turn",
        lambda **_kwargs: _FakeDecision(
            _sm_result(
                winning_action_metadata={
                    "response_mode": "hybrid",
                    "selected_media_card_ids": ["card-1"],
                    "route_reasoning": "product fit on document",
                    "route_source": "llm",
                }
            )
        ),
    )

    generated = {}

    def _generate(_action, context):
        generated["context"] = context
        return "Ответ"

    monkeypatch.setattr(bot.generator, "generate", _generate)

    bot.set_pending_media_meta(
        {
            "source_user_text": "посмотри документ и скажи, подойдет ли Lite?",
            "knowledge_cards": [
                {
                    "knowledge_id": "card-1",
                    "attachment_fingerprint": "fp-1",
                    "file_name": "doc.pdf",
                    "media_kind": "document",
                    "summary": "Документ клиента про текущие процессы.",
                    "facts": ["У клиента 3 магазина."],
                    "answer_context": "У клиента 3 магазина.",
                }
            ],
        }
    )

    bot.process("посмотри документ и скажи, подойдет ли Lite?")

    assert generated["context"]["media_route_mode"] == "hybrid"
    assert generated["context"]["kb_retrieved_facts"] == "KB FACT"
    assert "У клиента 3 магазина." in generated["context"]["selected_media_grounding"]
    assert "KB FACT" in generated["context"]["retrieved_facts"]
    assert "У клиента 3 магазина." in generated["context"]["retrieved_facts"]


def test_structural_action_ignores_media_route_for_generation(monkeypatch):
    bot = SalesBot(llm=_MediaBotLLM(), flow_name="autonomous")

    monkeypatch.setattr(bot.classifier, "classify", lambda *_args, **_kwargs: _mock_classification())
    monkeypatch.setattr(bot, "_analyze_tone", lambda *_args, **_kwargs: _mock_tone())
    monkeypatch.setattr(
        bot.generator,
        "prepare_response_context",
        lambda *_args, **_kwargs: _prepared_response_context("KB ONLY"),
    )
    monkeypatch.setattr(
        bot._orchestrator,
        "process_turn",
        lambda **_kwargs: _FakeDecision(
            _sm_result(
                action="stall_guard_nudge",
                winning_action_metadata={
                    "response_mode": "media_only",
                    "selected_media_card_ids": ["card-1"],
                    "route_reasoning": "should be ignored",
                    "route_source": "llm",
                },
            )
        ),
    )

    generated = {}

    def _generate(_action, context):
        generated["context"] = context
        return "Ответ"

    monkeypatch.setattr(bot.generator, "generate", _generate)

    bot.set_pending_media_meta(
        {
            "source_user_text": "что в документе?",
            "knowledge_cards": [
                {
                    "knowledge_id": "card-1",
                    "attachment_fingerprint": "fp-1",
                    "file_name": "doc.pdf",
                    "media_kind": "document",
                    "summary": "Это документ компании Альфа Логистик.",
                    "facts": ["Компания Альфа Логистик."],
                    "extracted_data": {"company_name": "Альфа Логистик"},
                    "answer_context": "Это документ компании Альфа Логистик.",
                }
            ],
        }
    )

    bot.process("что в документе?")

    assert generated["context"]["retrieved_facts"] == "KB ONLY"
    assert generated["context"]["media_route_mode"] == "normal_dialog"
    assert generated["context"]["selected_media_grounding"] == ""


def test_explicit_media_turn_context_takes_precedence_over_adapter_state(monkeypatch):
    bot = SalesBot(llm=_MediaBotLLM(), flow_name="autonomous")

    monkeypatch.setattr(bot.classifier, "classify", lambda *_args, **_kwargs: _mock_classification())
    monkeypatch.setattr(bot, "_analyze_tone", lambda *_args, **_kwargs: _mock_tone())
    monkeypatch.setattr(
        bot.generator,
        "prepare_response_context",
        lambda *_args, **_kwargs: _prepared_response_context("KB FACT"),
    )

    captured = {}
    def _process_turn(**kwargs):
        captured["media_turn_context"] = kwargs["media_turn_context"]
        return _FakeDecision(_sm_result())

    monkeypatch.setattr(bot._orchestrator, "process_turn", _process_turn)
    monkeypatch.setattr(bot.generator, "generate", lambda *_args, **_kwargs: "Ответ")

    bot.set_pending_media_meta(
        {
            "source_user_text": "adapter text",
            "knowledge_cards": [
                {
                    "knowledge_id": "adapter-card",
                    "attachment_fingerprint": "adapter-fp",
                    "summary": "Adapter card",
                    "facts": ["adapter"],
                }
            ],
        }
    )

    explicit_context = MediaTurnContext(
        raw_user_text="explicit text",
        attachment_only=False,
        source_session_id="sess-explicit",
        source_user_id="user-explicit",
        used_attachments=(),
        skipped_attachments=(),
        current_cards=(
            {
                "knowledge_id": "explicit-card",
                "attachment_fingerprint": "explicit-fp",
                "summary": "Explicit card",
                "facts": ["explicit"],
            },
        ),
        historical_candidates=(),
        safe_extracted_data={},
        safe_media_facts=("explicit",),
    )

    bot.process("combined text", media_turn_context=explicit_context)

    assert [card["knowledge_id"] for card in captured["media_turn_context"].current_cards] == ["explicit-card"]
