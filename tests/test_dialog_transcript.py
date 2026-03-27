from unittest.mock import Mock

from src.bot import SalesBot
from src.dialog_transcript import (
    DialogTranscript,
    project_history_from_context,
    render_dialogue_from_context,
)
from src.generator import ResponseGenerator, SafeDict


def _mk_history(count: int):
    return [{"user": f"u{i}", "bot": f"b{i}"} for i in range(count)]


def test_dialog_transcript_append_and_named_projections():
    transcript = DialogTranscript()
    transcript.append_turn_internal(user_text="u1", bot_text="b1", intent="i1", state="s1", action="a1")
    transcript.append_turn_internal(user_text="u2", bot_text="b2", intent="i2", state="s2", action="a2")

    turns = transcript.full_transcript()
    assert [turn.turn_index for turn in turns] == [0, 1]
    assert transcript.legacy_history_view() == [{"user": "u1", "bot": "b1"}, {"user": "u2", "bot": "b2"}]
    assert transcript.classifier_window() == transcript.legacy_history_view()
    assert transcript.decision_window() == transcript.legacy_history_view()
    assert transcript.prompt_window() == transcript.legacy_history_view()
    assert transcript.recent_bot_responses() == ["b1", "b2"]
    assert transcript.recent_user_messages() == ["u1", "u2"]


def test_project_history_from_context_prefers_transcript_over_legacy_history():
    transcript = DialogTranscript.from_legacy_history(_mk_history(6))
    projected = project_history_from_context(
        {
            "transcript": transcript,
            "history": [{"user": "legacy-user", "bot": "legacy-bot"}],
        },
        "verifier_window",
    )

    assert projected == _mk_history(6)[-4:]


def test_render_verbatim_dialogue_preserves_order_and_trims_head_only():
    transcript = DialogTranscript.from_legacy_history(
        [
            {"user": "ранний вопрос", "bot": "ранний ответ"},
            {"user": "середина", "bot": "ответ середина"},
            {"user": "последний вопрос", "bot": "последний ответ"},
        ]
    )

    full = transcript.render_verbatim_dialogue()
    assert full == (
        "Клиент: ранний вопрос\n"
        "Вы: ранний ответ\n"
        "Клиент: середина\n"
        "Вы: ответ середина\n"
        "Клиент: последний вопрос\n"
        "Вы: последний ответ"
    )

    trimmed = transcript.render_verbatim_dialogue(
        max_chars=len("Клиент: последний вопрос\nВы: последний ответ"),
    )
    assert trimmed == "Клиент: последний вопрос\nВы: последний ответ"
    assert "ранний вопрос" not in trimmed
    assert "середина" not in trimmed


def test_render_dialogue_from_context_prefers_transcript_over_legacy_history():
    transcript = DialogTranscript.from_legacy_history(
        [{"user": "истинный контекст", "bot": "истинный ответ"}]
    )
    context = {
        "transcript": transcript,
        "history": [{"user": "legacy-user", "bot": "legacy-bot"}],
    }

    rendered = render_dialogue_from_context(context, "generator")

    assert "истинный контекст" in rendered
    assert "legacy-user" not in rendered


def test_render_verbatim_dialogue_hard_caps_single_oversized_turn():
    transcript = DialogTranscript.from_legacy_history(
        [{"user": "x" * 200, "bot": "y" * 200}]
    )

    rendered = transcript.render_verbatim_dialogue(max_chars=80)

    assert len(rendered) <= 80
    assert rendered.startswith("...")
    assert rendered.endswith("y" * 77)


def test_fit_history_to_autonomous_prompt_never_exceeds_budget():
    transcript = DialogTranscript.from_legacy_history(
        [
            {"user": "коротко", "bot": "ок"},
            {"user": "x" * 5000, "bot": "y" * 5000},
        ]
    )
    context = {"transcript": transcript}
    variables = {"history": transcript.generator_dialogue_text()}
    template = "HEAD\n{history}\nTAIL"

    ResponseGenerator._fit_history_to_autonomous_prompt(
        template=template,
        variables=variables,
        context=context,
        max_prompt_chars=300,
    )

    prompt = template.format_map(SafeDict(variables))
    assert len(prompt) <= 300


def test_bot_commit_turn_updates_transcript_and_context_window(mock_llm):
    bot = SalesBot(llm=mock_llm, flow_name="autonomous", client_id="client-1")

    bot.commit_turn(
        user_message="Сколько стоит?",
        bot_message="Mini стоит 5000 тенге в месяц.",
        intent="price_question",
        confidence=0.91,
        action="autonomous_respond",
        state="greeting",
        next_state="autonomous_discovery",
        method="llm",
        extracted_data={},
        is_fallback=False,
        fallback_tier=None,
        fact_keys_used=["pricing.mini"],
        response_embedding=None,
        media_cards_to_store=None,
        reason_codes=["pricing_answered"],
        source_branch="generator_response",
    )

    assert bot.history == [{"user": "Сколько стоит?", "bot": "Mini стоит 5000 тенге в месяц."}]
    assert bot.transcript_status == "full"
    assert bot.transcript_provenance == "live"
    assert bot.degraded_continuity is False
    assert bot.last_action == "autonomous_respond"
    assert bot.last_intent == "price_question"
    assert bot.last_bot_message == "Mini стоит 5000 тенге в месяц."
    last_turn = bot.context_window.get_last_turn()
    assert last_turn is not None
    assert last_turn.user_message == "Сколько стоит?"
    assert last_turn.bot_response == "Mini стоит 5000 тенге в месяц."


def test_bot_history_append_updates_canonical_transcript(mock_llm):
    bot = SalesBot(llm=mock_llm, flow_name="autonomous", client_id="client-1")

    bot.history.append({"user": "u1", "bot": "b1"})

    assert list(bot.history) == [{"user": "u1", "bot": "b1"}]
    assert bot.transcript.legacy_history_view() == [{"user": "u1", "bot": "b1"}]
    assert bot.transcript_status == "full"
    assert bot.transcript_provenance == "live"


def test_classification_context_dialog_history_comes_from_transcript(mock_llm):
    bot = SalesBot(llm=mock_llm, flow_name="autonomous", client_id="client-1")
    bot.history = _mk_history(5)

    context = bot._get_classification_context()

    assert context["dialog_history"] == _mk_history(5)[-4:]


def test_tail_restore_marks_partial_and_degraded(mock_llm):
    bot = SalesBot(llm=mock_llm, flow_name="autonomous", client_id="client-1")
    bot.history = _mk_history(6)

    snapshot = bot.to_snapshot(compact_history=True, history_tail_size=4)
    restored = SalesBot.from_snapshot(snapshot, llm=mock_llm)

    assert restored.history == _mk_history(6)[-4:]
    assert restored.transcript_status == "partial"
    assert restored.transcript_provenance == "history_tail"
    assert restored.degraded_continuity is True


def test_generator_self_intro_guard_prefers_transcript_over_legacy_history():
    transcript = DialogTranscript.from_legacy_history(
        [{"user": "u1", "bot": "Здравствуйте! Меня зовут Айбота, я ваш консультант Wipon."}]
    )
    context = {
        "transcript": transcript,
        "history": [{"user": "legacy-user", "bot": "legacy-bot"}],
        "user_message": "Сколько стоит?",
        "is_first_bot_reply": False,
    }

    result = ResponseGenerator._suppress_repeated_self_intro(
        "Здравствуйте! Меня зовут Айбота, я ваш консультант Wipon. Чем могу помочь?",
        context,
        is_greeting_turn=False,
    )

    assert "меня зовут айбота" not in result.lower()
    assert result


def test_generator_recent_fact_helpers_prefer_transcript_over_legacy_history():
    generator = ResponseGenerator(llm=Mock())
    transcript = DialogTranscript.from_legacy_history(
        [
            {"user": "У нас одна точка", "bot": "Поняла."},
            {"user": "Сейчас уже 7 точек", "bot": "Хорошо, учту."},
        ]
    )
    context = {
        "transcript": transcript,
        "history": [{"user": "legacy-user", "bot": "legacy-bot"}],
        "user_message": "Подберите тариф",
    }

    assert generator._extract_points_from_context(context) == 7
