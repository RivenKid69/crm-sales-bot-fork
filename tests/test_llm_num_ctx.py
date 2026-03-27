from copy import deepcopy
from unittest.mock import MagicMock, patch

from pydantic import BaseModel

from src.llm import OllamaClient
from src.settings import DEFAULTS, DotDict, reload_settings, validate_settings


class StructuredSchema(BaseModel):
    answer: str


def _ollama_response(content: str) -> MagicMock:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"message": {"content": content}}
    return response


def _openai_response(content: str) -> MagicMock:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "choices": [{"message": {"content": content}}],
    }
    return response


def test_reload_settings_exposes_num_ctx_16384():
    settings = reload_settings()

    assert settings.llm.num_ctx == 16384


def test_validate_settings_rejects_non_integer_num_ctx():
    settings_dict = deepcopy(DEFAULTS)
    settings_dict["llm"]["num_ctx"] = "16384"

    errors = validate_settings(DotDict(settings_dict))

    assert "llm.num_ctx должен быть целым числом" in errors


def test_validate_settings_rejects_small_num_ctx():
    settings_dict = deepcopy(DEFAULTS)
    settings_dict["llm"]["num_ctx"] = 1024

    errors = validate_settings(DotDict(settings_dict))

    assert "llm.num_ctx должен быть >= 2048" in errors


def test_generate_structured_sends_num_ctx_and_records_trace():
    client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)

    with patch("requests.post", return_value=_ollama_response('{"answer": "ok"}')) as mock_post:
        result, trace = client.generate_structured("prompt", StructuredSchema, return_trace=True)

    assert result is not None
    payload = mock_post.call_args.kwargs["json"]
    assert payload["options"]["num_ctx"] == 16384
    assert trace.num_ctx_requested == 16384
    assert trace.to_dict()["num_ctx_requested"] == 16384
    assert trace.to_compact_dict()["num_ctx_requested"] == 16384


def test_generate_sends_num_ctx_and_records_trace():
    client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)

    with patch("requests.post", return_value=_ollama_response("freeform ok")) as mock_post:
        result, trace = client.generate("prompt", return_trace=True)

    assert result == "freeform ok"
    payload = mock_post.call_args.kwargs["json"]
    assert payload["options"]["num_ctx"] == 16384
    assert trace.num_ctx_requested == 16384


def test_generate_multimodal_sends_num_ctx_and_records_trace():
    client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)

    with patch("requests.post", return_value=_ollama_response("multimodal ok")) as mock_post:
        result, trace = client.generate_multimodal(
            "prompt",
            images=["ZmFrZV9pbWFnZQ=="],
            return_trace=True,
        )

    assert result == "multimodal ok"
    payload = mock_post.call_args.kwargs["json"]
    assert payload["options"]["num_ctx"] == 16384
    assert trace.num_ctx_requested == 16384


def test_openai_compatible_branch_does_not_inject_num_ctx():
    client = OllamaClient(
        api_format="openai",
        enable_retry=False,
        enable_circuit_breaker=False,
    )

    with patch("requests.post", return_value=_openai_response("openai ok")) as mock_post:
        result, trace = client.generate("prompt", return_trace=True)

    assert result == "openai ok"
    payload = mock_post.call_args.kwargs["json"]
    assert "num_ctx" not in str(payload)
    assert trace.num_ctx_requested == 0
