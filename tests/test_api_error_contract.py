"""
Tests for structured API error contract in src/api.py.
"""

from pathlib import Path

from fastapi.testclient import TestClient
import pytest


def _valid_payload() -> dict:
    return {
        "session_id": "BOT_7000",
        "user_id": "77022951810",
        "channel": "whatsapp",
        "message": {"text": "Привет", "timestamp_ms": 1770801587839},
    }


def _valid_sula_payload() -> list[dict]:
    return [
        {
            "id": "evt_01kkbny52vw60ydk3bqygtycpp",
            "timestamp": 1773139858523,
            "session": "BOT_6921_test",
            "client_text": "Здравствуйте, я из Астаны.",
            "cleint_phone": "77710107606",
        }
    ]


@pytest.fixture(autouse=True)
def _disable_startup_warmup(monkeypatch):
    import src.api as api_mod

    monkeypatch.setattr(api_mod, "_start_startup_warmup", lambda: None)


def test_process_returns_401_with_structured_error(monkeypatch, tmp_path: Path):
    import src.api as api_mod

    monkeypatch.setattr(api_mod, "API_KEY", "test-key")
    monkeypatch.setattr(api_mod, "DB_PATH", str(tmp_path / "test_401.db"))

    with TestClient(api_mod.app) as client:
        resp = client.post(
            "/api/v1/process",
            headers={"Authorization": "Bearer wrong-key"},
            json=_valid_payload(),
        )

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_process_returns_401_with_structured_error_when_auth_missing(monkeypatch, tmp_path: Path):
    import src.api as api_mod

    monkeypatch.setattr(api_mod, "API_KEY", "test-key")
    monkeypatch.setattr(api_mod, "DB_PATH", str(tmp_path / "test_401_missing_auth.db"))

    with TestClient(api_mod.app) as client:
        resp = client.post("/api/v1/process", json=_valid_payload())

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_process_returns_400_with_structured_error_for_invalid_payload(monkeypatch, tmp_path: Path):
    import src.api as api_mod

    monkeypatch.setattr(api_mod, "API_KEY", "test-key")
    monkeypatch.setattr(api_mod, "DB_PATH", str(tmp_path / "test_400.db"))

    with TestClient(api_mod.app) as client:
        resp = client.post(
            "/api/v1/process",
            headers={"Authorization": "Bearer test-key"},
            json={"session_id": "BOT_7000", "user_id": "77022951810"},
        )

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "BAD_REQUEST"


def test_process_returns_500_with_structured_error_for_internal_exception(monkeypatch, tmp_path: Path):
    import src.api as api_mod

    monkeypatch.setattr(api_mod, "API_KEY", "test-key")
    monkeypatch.setattr(api_mod, "DB_PATH", str(tmp_path / "test_500.db"))

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(api_mod, "_load_snapshot", boom)

    with TestClient(api_mod.app) as client:
        resp = client.post(
            "/api/v1/process",
            headers={"Authorization": "Bearer test-key"},
            json=_valid_payload(),
        )

    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "INTERNAL"


def test_get_user_profile_returns_404_with_structured_error(monkeypatch, tmp_path: Path):
    import src.api as api_mod

    monkeypatch.setattr(api_mod, "API_KEY", "test-key")
    monkeypatch.setattr(api_mod, "DB_PATH", str(tmp_path / "test_profile_404.db"))

    with TestClient(api_mod.app) as client:
        resp = client.get(
            "/api/v1/users/non-existing-user/profile",
            headers={"Authorization": "Bearer test-key"},
        )

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_ready_returns_503_while_warmup_running(monkeypatch, tmp_path: Path):
    import src.api as api_mod

    monkeypatch.setattr(api_mod, "DB_PATH", str(tmp_path / "ready_running.db"))
    monkeypatch.setattr(
        api_mod,
        "_dependency_snapshot",
        lambda: {"db": True, "llm": True, "tei_embed": True, "tei_rerank": True},
    )
    monkeypatch.setattr(
        api_mod,
        "_get_startup_warmup_state",
        lambda: {
            "status": "running",
            "started_at": 1.0,
            "finished_at": None,
            "details": {},
            "errors": [],
        },
    )

    with TestClient(api_mod.app) as client:
        resp = client.get("/ready")

    assert resp.status_code == 503
    assert resp.json()["status"] == "not_ready"


def test_ready_returns_200_when_dependencies_and_warmup_are_ready(monkeypatch, tmp_path: Path):
    import src.api as api_mod

    monkeypatch.setattr(api_mod, "DB_PATH", str(tmp_path / "ready_ok.db"))
    monkeypatch.setattr(
        api_mod,
        "_dependency_snapshot",
        lambda: {"db": True, "llm": True, "tei_embed": True, "tei_rerank": True},
    )
    monkeypatch.setattr(
        api_mod,
        "_get_startup_warmup_state",
        lambda: {
            "status": "ready",
            "started_at": 1.0,
            "finished_at": 2.0,
            "details": {"kb_embeddings_ready": True},
            "errors": [],
        },
    )

    with TestClient(api_mod.app) as client:
        resp = client.get("/ready")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ready"
    assert payload["dependencies"]["llm"] is True
    assert payload["warmup"]["status"] == "ready"


def test_process_accepts_sula_payload_and_returns_ai_text(monkeypatch, tmp_path: Path):
    import src.api as api_mod

    captured = {}

    def fake_process(req):
        captured["session_id"] = req.session_id
        captured["user_id"] = req.user_id
        captured["text"] = req.message.text
        return {
            "answer": "Здравствуйте! Чем могу помочь?",
            "meta": {"model": "test-model", "processing_ms": 123, "kb_used": False},
        }

    monkeypatch.setattr(api_mod, "API_KEY", "test-key")
    monkeypatch.setattr(api_mod, "DB_PATH", str(tmp_path / "test_sula.db"))
    monkeypatch.setattr(api_mod, "_process_message_request", fake_process)

    with TestClient(api_mod.app) as client:
        resp = client.post(
            "/api/v1/process",
            headers={"Authorization": "Bearer test-key"},
            json=_valid_sula_payload(),
        )

    assert resp.status_code == 200
    assert resp.json() == [
        {
            "id": "evt_01kkbny52vw60ydk3bqygtycpp",
            "timestamp": 1773139858523,
            "session": "BOT_6921_test",
            "client_text": "Здравствуйте, я из Астаны.",
            "cleint_phone": "77710107606",
            "ai_text": "Здравствуйте! Чем могу помочь?",
        }
    ]
    assert captured == {
        "session_id": "BOT_6921_test",
        "user_id": "77710107606",
        "text": "Здравствуйте, я из Астаны.",
    }


def test_process_sula_endpoint_accepts_single_object(monkeypatch, tmp_path: Path):
    import src.api as api_mod

    monkeypatch.setattr(api_mod, "API_KEY", "test-key")
    monkeypatch.setattr(api_mod, "DB_PATH", str(tmp_path / "test_sula_single.db"))
    monkeypatch.setattr(
        api_mod,
        "_process_message_request",
        lambda _req: {
            "answer": "Ответ от бота",
            "meta": {"model": "test-model", "processing_ms": 1, "kb_used": False},
        },
    )

    payload = _valid_sula_payload()[0]

    with TestClient(api_mod.app) as client:
        resp = client.post(
            "/api/v1/process/sula",
            headers={"Authorization": "Bearer test-key"},
            json=payload,
        )

    assert resp.status_code == 200
    assert resp.json()["ai_text"] == "Ответ от бота"
    assert resp.json()["session"] == payload["session"]
