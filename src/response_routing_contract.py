from __future__ import annotations

from typing import Any, Dict, Optional


CANONICAL_RESPONSE_MODES = frozenset({"normal_dialog", "media_only", "hybrid"})
AUTONOMOUS_RESPONSE_STATES = frozenset(
    {"greeting", "soft_close", "payment_ready", "video_call_scheduled"}
)
AUTONOMOUS_RESPONSE_TEMPLATE_KEYS = frozenset(
    {
        "autonomous_respond",
        "autonomous_media_only",
        "continue_current_goal",
        "greet_back",
        "answer_with_facts",
        "clarify_one_question",
        "summarize_and_clarify",
        "nudge_progress",
        "reframe_value",
        "handle_repeated_objection",
        "empathize_and_redirect",
        "objection_limit_reached",
        "blocking_with_pricing",
        "escalate_to_human",
        "soft_close",
        "close",
        "handle_farewell",
    }
)


def normalize_response_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    if mode not in CANONICAL_RESPONSE_MODES:
        return "normal_dialog"
    return mode


def build_response_routing_context(
    *,
    context: Optional[Dict[str, Any]] = None,
    state: Any = None,
    requested_action: Any = None,
    selected_template_key: Any = None,
    response_mode: Any = None,
) -> Dict[str, Any]:
    routing_context = dict(context or {})
    resolved_mode = normalize_response_mode(
        response_mode
        if response_mode is not None
        else routing_context.get("response_mode", routing_context.get("media_route_mode"))
    )
    resolved_template_key = str(
        selected_template_key
        if selected_template_key is not None
        else routing_context.get("selected_template_key", routing_context.get("selected_template", ""))
        or ""
    ).strip()
    resolved_requested_action = str(
        requested_action
        if requested_action is not None
        else routing_context.get("requested_action", routing_context.get("action", ""))
        or ""
    ).strip()
    resolved_state = (
        str(state or "")
        if state is not None
        else str(routing_context.get("state", "") or "")
    ).strip()

    routing_context["response_mode"] = resolved_mode
    routing_context["media_route_mode"] = resolved_mode
    routing_context["requested_action"] = resolved_requested_action
    routing_context["selected_template_key"] = resolved_template_key
    routing_context["selected_template"] = resolved_template_key
    if resolved_state:
        routing_context["state"] = resolved_state
    return routing_context


def is_autonomous_response_context(
    *,
    state: Any = None,
    selected_template_key: Any = None,
    requested_action: Any = None,
    context: Optional[Dict[str, Any]] = None,
) -> bool:
    routing_context = build_response_routing_context(
        context=context,
        state=state,
        requested_action=requested_action,
        selected_template_key=selected_template_key,
    )
    resolved_state = str(routing_context.get("state", "") or "").strip().lower()
    resolved_template_key = str(routing_context.get("selected_template_key", "") or "").strip().lower()
    resolved_requested_action = str(routing_context.get("requested_action", "") or "").strip().lower()

    if resolved_state.startswith("autonomous_"):
        return True
    if resolved_state in AUTONOMOUS_RESPONSE_STATES:
        return True
    if resolved_template_key in AUTONOMOUS_RESPONSE_TEMPLATE_KEYS:
        return True
    return resolved_requested_action in AUTONOMOUS_RESPONSE_TEMPLATE_KEYS
