from src.generator_autonomous import (
    build_address_instruction,
    count_name_mentions_in_history,
)
from src.generator import ResponseGenerator


def test_count_name_mentions_in_history_tracks_first_name_and_full_name() -> None:
    history = [
        {"bot": "Алия, тариф Mini стоит 5 000 тенге."},
        {"bot": "Поддержка работает ежедневно."},
        {"bot": "Алия Сейтова, подключение займёт 1 день."},
    ]

    assert count_name_mentions_in_history(history, "Алия Сейтова") == 2
    assert count_name_mentions_in_history(history, "Алия Сейтова", recent_bot_turns=2) == 1


def test_build_address_instruction_blocks_name_if_used_recently() -> None:
    instruction = build_address_instruction(
        collected={"contact_name": "Марат Сейткали"},
        history=[
            {"bot": "Здравствуйте, меня зовут Айбота."},
            {"bot": "Марат Сейткали, Standard подойдёт для двух точек."},
        ],
    )

    assert "НЕ используй имя" in instruction
    assert "последних 4 ответов" in instruction


def test_build_address_instruction_allows_sparse_name_usage() -> None:
    instruction = build_address_instruction(
        collected={"contact_name": "Айгерим"},
        history=[
            {"bot": "Здравствуйте, меня зовут Айбота."},
            {"bot": "Lite стоит 150 000 тенге в год."},
            {"bot": "Поддержка работает ежедневно."},
            {"bot": "Интеграция с Kaspi доступна в Lite."},
        ],
    )

    assert "максимум 1 раз за 4 ответа" in instruction
    assert "НЕ используй имя" not in instruction


def test_suppress_repeated_client_name_removes_recent_repeat_and_leading_name() -> None:
    response = "Айгерим, тариф Lite стоит 150 000 тенге в год."
    context = {
        "collected_data": {"contact_name": "Айгерим"},
        "history": [
            {"bot": "Здравствуйте, меня зовут Айбота."},
            {"bot": "Айгерим, у нас есть интеграция с Kaspi."},
        ],
    }

    cleaned = ResponseGenerator._suppress_repeated_client_name(response, context)

    assert cleaned == "тариф Lite стоит 150 000 тенге в год."


def test_suppress_repeated_client_name_strips_leading_name_even_on_first_allowed_use() -> None:
    response = "Алия, тариф Mini стоит 5 000 тенге в месяц."
    context = {
        "collected_data": {"contact_name": "Алия"},
        "history": [],
    }

    cleaned = ResponseGenerator._suppress_repeated_client_name(response, context)

    assert cleaned == "тариф Mini стоит 5 000 тенге в месяц."


def test_build_address_instruction_skips_name_question_for_specific_product_request() -> None:
    instruction = build_address_instruction(
        collected={},
        history=[],
        state="greeting",
        intent="question_specific_product",
        user_message="Мне нужен комплект Standard+ в Алматы",
    )

    low = instruction.lower()
    assert "не спрашивай имя" in low
    assert "как к вам обращаться" not in low


def test_build_address_instruction_skips_name_question_for_named_product_even_if_intent_generic() -> None:
    instruction = build_address_instruction(
        collected={},
        history=[],
        state="greeting",
        intent="situation_provided",
        user_message="Здравствуйте, хочу тариф Lite для одного магазина",
    )

    low = instruction.lower()
    assert "не спрашивай имя" in low
    assert "как к вам обращаться" not in low
