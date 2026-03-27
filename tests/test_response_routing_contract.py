from src.response_boundary_validator import ResponseBoundaryValidator
from src.response_routing_contract import (
    build_response_routing_context,
    is_autonomous_response_context,
)


def test_soft_close_is_autonomous_response_context_without_selected_template():
    assert is_autonomous_response_context(state="soft_close", requested_action="autonomous_respond") is True


def test_terminal_states_are_autonomous_response_contexts():
    assert is_autonomous_response_context(state="payment_ready") is True
    assert is_autonomous_response_context(state="video_call_scheduled") is True


def test_build_response_routing_context_sets_canonical_aliases():
    context = build_response_routing_context(
        context={"media_route_mode": "media_only"},
        requested_action="autonomous_respond",
        selected_template_key="autonomous_media_only",
    )

    assert context["response_mode"] == "media_only"
    assert context["media_route_mode"] == "media_only"
    assert context["selected_template_key"] == "autonomous_media_only"
    assert context["selected_template"] == "autonomous_media_only"


def test_boundary_validator_uses_selected_template_key_contract():
    validator = ResponseBoundaryValidator()

    assert validator._is_autonomous_flow_context(  # noqa: SLF001
        {"state": "soft_close", "selected_template_key": "soft_close"}
    ) is True


def test_boundary_validator_direct_helpers_accept_legacy_selected_template():
    validator = ResponseBoundaryValidator()

    violations = validator._detect_violations(  # noqa: SLF001
        "Здравствуйте! Я Wipon-ассистент. Как могу помочь?",
        {"selected_template": "greeting"},
    )
    sanitized = validator._sanitize_mid_conversation_greeting(  # noqa: SLF001
        "Здравствуйте! Я ваш ассистент.",
        {"selected_template": "greeting"},
    )

    assert "mid_conversation_greeting" not in violations
    assert sanitized == "Здравствуйте! Я ваш ассистент."
