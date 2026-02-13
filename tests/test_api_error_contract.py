"""
Tests for structured API error contract in src/api.py.
"""

from pathlib import Path

from fastapi.testclient import TestClient


def _valid_payload() -> dict:
    return {
        "session_id": "BOT_7000",
        "user_id": "77022951810",
        "channel": "whatsapp",
        "message": {"text": "Привет", "timestamp_ms": 1770801587839},
    }


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
