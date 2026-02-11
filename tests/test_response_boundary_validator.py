"""Tests for final response boundary validator."""

from unittest.mock import Mock

import pytest

from src.feature_flags import flags
from src.response_boundary_validator import ResponseBoundaryValidator


@pytest.fixture(autouse=True)
def reset_flags():
    flags.clear_all_overrides()
    flags.set_override("response_boundary_validator", True)
    flags.set_override("response_boundary_retry", True)
    flags.set_override("response_boundary_fallback", True)
    yield
    flags.clear_all_overrides()


def test_pricing_currency_locale_is_canonicalized_to_tenge():
    validator = ResponseBoundaryValidator()
    result = validator.validate_response(
        "Стоимость 15000 руб. или 200₽ в месяц.",
        context={"intent": "price_question", "action": "answer_with_pricing"},
        llm=None,
    )
    assert "руб" not in result.response.lower()
    assert "₽" not in result.response
    assert "₸" in result.response


def test_known_typo_is_fixed_without_retry():
    validator = ResponseBoundaryValidator()
    result = validator.validate_response(
        "Хорошо, присылну детали сегодня.",
        context={"intent": "info_provided", "action": "continue_current_goal"},
        llm=None,
    )
    assert "присылну" not in result.response.lower()
    assert "пришлю" in result.response.lower()
    assert result.retry_used is False


def test_retry_is_used_once_then_deterministic_fallback():
    validator = ResponseBoundaryValidator()
    llm = Mock()
    llm.generate = Mock(return_value="Оставляю руб и артефакт . — без исправлений")
    validator._sanitize = Mock(side_effect=lambda text, ctx: text)

    result = validator.validate_response(
        "Цена 1000 руб. . — пришлю детали",
        context={"intent": "price_question", "action": "answer_with_pricing_direct"},
        llm=llm,
    )

    assert llm.generate.call_count == 1
    assert result.retry_used is True
    assert result.fallback_used is True
    assert "руб" not in result.response.lower()
    assert "₸" in result.response
