"""
Regression tests for "бот здоровается в середине разговора" bug.

Covers:
1. KB data integrity — no facts: entry starts with Здравствуйте
2. generator strip — re.sub removes greeting opener from retrieved_facts
3. validator detect — mid_conversation_greeting fired for non-greeting templates
4. validator detect — NOT fired for greeting template
5. validator sanitize — greeting stripped, text capitalised, name preserved
6. validator sanitize safety — empty/short remainder returns original
"""

import re

import pytest
import yaml


# ---------------------------------------------------------------------------
# 1. KB data integrity
# ---------------------------------------------------------------------------

KB_FILES = [
    "src/knowledge/data/regions.yaml",
    "src/knowledge/data/support.yaml",
    "src/knowledge/data/pricing.yaml",
]


@pytest.mark.parametrize("path", KB_FILES)
def test_kb_no_greeting_in_facts(path):
    """No facts: value should start with Здравствуйте after the fix."""
    with open(path, encoding="utf-8") as f:
        content = f.read()
    # Match "facts:" followed (possibly after whitespace on the same line) by Здравствуйте
    pattern = re.compile(r"facts:\s*Здравствуйте", re.IGNORECASE)
    matches = pattern.findall(content)
    assert matches == [], (
        f"{path} still has {len(matches)} facts: entry(ies) starting with Здравствуйте: {matches}"
    )


# ---------------------------------------------------------------------------
# 2. generator.py safety-net strip
# ---------------------------------------------------------------------------

_GREETING_STRIP = re.compile(r'(?m)^Здравствуйте[!.]?\s*', )


def _apply_generator_strip(text: str) -> str:
    """Mirrors the logic added to generator.py after _redact_credentials."""
    return _GREETING_STRIP.sub('', text)


def test_generator_strip_exclamation():
    raw = "Здравствуйте! Наш продукт подходит для розницы."
    result = _apply_generator_strip(raw)
    assert "Здравствуйте" not in result
    assert "Наш продукт подходит для розницы." in result


def test_generator_strip_period():
    raw = "Здравствуйте. Сможем подключить за 1 день."
    result = _apply_generator_strip(raw)
    assert "Здравствуйте" not in result
    assert "Сможем подключить за 1 день." in result


def test_generator_strip_multiline():
    raw = "Здравствуйте! Первая строка.\nВторая строка без приветствия."
    result = _apply_generator_strip(raw)
    assert "Здравствуйте" not in result
    assert "Первая строка." in result
    assert "Вторая строка без приветствия." in result


# ---------------------------------------------------------------------------
# 3 & 4. ResponseBoundaryValidator — detect
# ---------------------------------------------------------------------------

from src.response_boundary_validator import ResponseBoundaryValidator  # noqa: E402

validator = ResponseBoundaryValidator()

NON_GREETING_TEMPLATES = [
    "autonomous_respond",
    "answer_with_pricing",
    "autonomous_closing",
    "continue_current_goal",
    "handle_objection",
    "",  # unknown/empty — should still be checked
]


@pytest.mark.parametrize("tmpl", NON_GREETING_TEMPLATES)
def test_validator_detects_greeting_in_non_greeting_template(tmpl):
    response = "Здравствуйте! Для вашего магазина отлично подойдёт тариф Стандарт."
    ctx = {"selected_template": tmpl}
    violations = validator._detect_violations(response, ctx)
    assert "mid_conversation_greeting" in violations, (
        f"Expected mid_conversation_greeting for template={tmpl!r}"
    )


@pytest.mark.parametrize("greeting", [
    "Добрый день, Айгерим! Рады видеть вас.",
    "Добрый вечер! Чем могу помочь?",
    "Доброе утро! Wipon готов к работе.",
])
def test_validator_detects_various_greetings(greeting):
    ctx = {"selected_template": "autonomous_respond"}
    violations = validator._detect_violations(greeting, ctx)
    assert "mid_conversation_greeting" in violations


def test_validator_no_detect_for_greeting_template():
    """Initial greeting response must NOT be flagged."""
    response = "Здравствуйте! Я Wipon-ассистент. Как могу помочь?"
    ctx = {"selected_template": "greeting"}
    violations = validator._detect_violations(response, ctx)
    assert "mid_conversation_greeting" not in violations


# ---------------------------------------------------------------------------
# 5. ResponseBoundaryValidator — sanitize
# ---------------------------------------------------------------------------

def test_sanitize_strips_greeting_no_name():
    response = "Здравствуйте! Для вашего магазина подойдёт тариф Стандарт."
    ctx = {"selected_template": "autonomous_respond"}
    result = validator._sanitize_mid_conversation_greeting(response, ctx)
    assert not result.startswith("Здравствуйте")
    assert "Для вашего магазина подойдёт тариф Стандарт." in result


def test_sanitize_strips_greeting_name_preserved():
    """Greeting stripped; name+text after comma preserved."""
    response = "Здравствуйте, Айгерим! Для вашего магазина подойдёт тариф Стандарт."
    ctx = {"selected_template": "autonomous_respond"}
    result = validator._sanitize_mid_conversation_greeting(response, ctx)
    # Pattern strips up to the first \s* after [,!.] — so "Айгерим! ..." remains
    assert "Айгерим" in result
    assert not result.startswith("Здравствуйте")


def test_sanitize_capitalises_first_letter():
    """If stripped result starts with lowercase, capitalise it."""
    # Simulate a case where stripping leaves lowercase start
    response = "Добрый день, а наш продукт подходит для розницы."
    ctx = {"selected_template": "autonomous_respond"}
    result = validator._sanitize_mid_conversation_greeting(response, ctx)
    assert result[0].isupper()


# ---------------------------------------------------------------------------
# 6. sanitize safety — short remainder returns original
# ---------------------------------------------------------------------------

def test_sanitize_safety_short_remainder():
    """If stripping leaves <10 chars, original is returned unchanged."""
    response = "Здравствуйте! ок"
    ctx = {"selected_template": "autonomous_respond"}
    result = validator._sanitize_mid_conversation_greeting(response, ctx)
    assert result == response


def test_sanitize_greeting_template_untouched():
    """Initial greeting template response is never modified."""
    response = "Здравствуйте! Я ваш ассистент."
    ctx = {"selected_template": "greeting"}
    result = validator._sanitize_mid_conversation_greeting(response, ctx)
    assert result == response
