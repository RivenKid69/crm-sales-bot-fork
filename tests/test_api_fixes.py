"""
Tests for api.py bug fixes:

BUG 1: bot.enable_tracing = True was a no-op in from_snapshot() path.
       SalesBot stores tracing as _enable_decision_tracing (private).
       Fix: from_snapshot() now accepts enable_tracing parameter.

BUG 2: _init_db() lacked PRAGMA journal_mode=WAL.
       FastAPI runs sync endpoints in a thread pool, so concurrent
       SQLite writes without WAL cause "database is locked" errors.
       Fix: _init_db() now sets WAL mode.
"""

import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
import types
from unittest.mock import MagicMock

import pytest
from src.media_preprocessor import PreparedMessage


def _import_api_module_with_fastapi_stub(monkeypatch):
    fastapi_mod = types.ModuleType("fastapi")
    fastapi_concurrency = types.ModuleType("fastapi.concurrency")
    fastapi_exceptions = types.ModuleType("fastapi.exceptions")
    fastapi_responses = types.ModuleType("fastapi.responses")

    class _FakeFastAPI:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def exception_handler(self, *_args, **_kwargs):
            def decorator(fn):
                return fn

            return decorator

        def get(self, *_args, **_kwargs):
            def decorator(fn):
                return fn

            return decorator

        def post(self, *_args, **_kwargs):
            def decorator(fn):
                return fn

            return decorator

    class _FakeJSONResponse:
        def __init__(self, status_code=200, content=None):
            self.status_code = status_code
            self.content = content

    class _FakeRequestValidationError(Exception):
        def errors(self):
            return []

    fastapi_mod.Depends = lambda value=None: value
    fastapi_mod.FastAPI = _FakeFastAPI
    fastapi_mod.Header = lambda default=None: default
    fastapi_mod.Request = object
    fastapi_concurrency.run_in_threadpool = lambda func, *args, **kwargs: func(*args, **kwargs)
    fastapi_exceptions.RequestValidationError = _FakeRequestValidationError
    fastapi_responses.JSONResponse = _FakeJSONResponse

    monkeypatch.setitem(sys.modules, "fastapi", fastapi_mod)
    monkeypatch.setitem(sys.modules, "fastapi.concurrency", fastapi_concurrency)
    monkeypatch.setitem(sys.modules, "fastapi.exceptions", fastapi_exceptions)
    monkeypatch.setitem(sys.modules, "fastapi.responses", fastapi_responses)
    sys.modules.pop("src.api", None)

    import src.api as api_mod

    return api_mod


# ---------------------------------------------------------------------------
# BUG 2 tests: SQLite WAL mode
# ---------------------------------------------------------------------------

class TestInitDbWalMode:
    """Verify _init_db() sets WAL journal mode and creates tables."""

    def test_init_db_creates_tables(self, tmp_path, monkeypatch):
        """_init_db() must create conversations and user_profiles tables."""
        api_mod = _import_api_module_with_fastapi_stub(monkeypatch)

        db_path = str(tmp_path / "test.db")
        original = api_mod.DB_PATH
        api_mod.DB_PATH = db_path
        try:
            api_mod._init_db()

            conn = sqlite3.connect(db_path)
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            conn.close()

            assert "conversations" in tables
            assert "user_profiles" in tables
        finally:
            api_mod.DB_PATH = original

    def test_init_db_sets_wal_mode(self, tmp_path, monkeypatch):
        """_init_db() must set journal_mode=WAL for concurrent access."""
        api_mod = _import_api_module_with_fastapi_stub(monkeypatch)

        db_path = str(tmp_path / "test_wal.db")
        original = api_mod.DB_PATH
        api_mod.DB_PATH = db_path
        try:
            api_mod._init_db()

            # WAL persists across connections once set
            conn = sqlite3.connect(db_path)
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            conn.close()

            assert mode == "wal", f"Expected WAL mode, got {mode}"
        finally:
            api_mod.DB_PATH = original

    def test_concurrent_writes_succeed_with_wal(self, tmp_path, monkeypatch):
        """Multiple threads writing simultaneously must not raise 'database is locked'."""
        api_mod = _import_api_module_with_fastapi_stub(monkeypatch)

        db_path = str(tmp_path / "test_concurrent.db")
        original = api_mod.DB_PATH
        api_mod.DB_PATH = db_path
        try:
            api_mod._init_db()

            errors = []
            barrier = threading.Barrier(4)

            def writer(session_id, user_id):
                try:
                    barrier.wait(timeout=5)
                    snapshot = {"state": "test", "turn": 1}
                    api_mod._save_snapshot(session_id, user_id, snapshot)
                except Exception as e:
                    errors.append(e)

            threads = [
                threading.Thread(target=writer, args=(f"s{i}", f"u{i}"))
                for i in range(4)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)

            assert errors == [], f"Concurrent writes failed: {errors}"

            # Verify all 4 rows written
            conn = sqlite3.connect(db_path)
            count = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            conn.close()
            assert count == 4
        finally:
            api_mod.DB_PATH = original

    def test_snapshot_roundtrip(self, tmp_path, monkeypatch):
        """_save_snapshot then _load_snapshot must return identical data."""
        api_mod = _import_api_module_with_fastapi_stub(monkeypatch)

        db_path = str(tmp_path / "test_roundtrip.db")
        original = api_mod.DB_PATH
        api_mod.DB_PATH = db_path
        try:
            api_mod._init_db()

            data = {"flow_name": "autonomous", "state": "discovery", "turn": 3}
            api_mod._save_snapshot("sess1", "user1", data)
            loaded = api_mod._load_snapshot("sess1", "user1")

            assert loaded == data
        finally:
            api_mod.DB_PATH = original

    def test_process_bootstraps_media_knowledge_for_new_session(self, tmp_path, monkeypatch):
        api_mod = _import_api_module_with_fastapi_stub(monkeypatch)

        db_path = str(tmp_path / "bootstrap.db")
        original = api_mod.DB_PATH
        api_mod.DB_PATH = db_path
        try:
            api_mod._init_db()

            conn = sqlite3.connect(db_path)
            conn.execute(
                """
                INSERT INTO user_profiles (
                    session_id, user_id, company_name, business_type,
                    pain_points, interested_features, objection_types, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "old-session",
                    "user-1",
                    "Альфа Логистик",
                    "логистика",
                    json.dumps(["нет контроля остатков"], ensure_ascii=False),
                    json.dumps([], ensure_ascii=False),
                    json.dumps([], ensure_ascii=False),
                    time.time(),
                ),
            )
            conn.execute(
                """
                INSERT INTO media_knowledge (
                    user_id, session_id, knowledge_id, attachment_fingerprint,
                    file_name, media_kind, source_user_text, summary,
                    facts_json, extracted_data_json, answer_context,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "user-1",
                    "old-session",
                    "card-1",
                    "fp-1",
                    "doc.pdf",
                    "document",
                    "посмотрите документ",
                    "Это документ компании Альфа Логистик.",
                    json.dumps(["Компания Альфа Логистик."], ensure_ascii=False),
                    json.dumps({"company_name": "Альфа Логистик"}, ensure_ascii=False),
                    "Это документ компании Альфа Логистик.",
                    time.time(),
                    time.time(),
                ),
            )
            conn.commit()
            conn.close()

            captured = {}

            class _FakeBot:
                state_machine = types.SimpleNamespace(is_final=lambda: False)

                def hydrate_external_memory(self, *, profile_data=None, media_cards=None):
                    captured["profile_data"] = profile_data
                    captured["media_cards"] = media_cards

                def set_pending_media_meta(self, *_args, **_kwargs):
                    pass

                def process(self, _text, *, media_turn_context=None):
                    captured["media_turn_context"] = media_turn_context
                    return {"response": "ok", "decision_trace": None}

            class _FakeSessionManager:
                def __init__(self):
                    self.bot = _FakeBot()

                def serialize_inactive_final_sessions(self, *_args, **_kwargs):
                    return 0

                def run_session_job(self, _session_id, *, client_id=None, job):
                    captured["run_session_job_client_id"] = client_id
                    return job()

                def get_or_create_with_status(self, *_args, **_kwargs):
                    return types.SimpleNamespace(bot=self.bot, source="new")

                def touch(self, *_args, **_kwargs):
                    return True

            monkeypatch.setattr(api_mod, "_llm", MagicMock())
            monkeypatch.setattr(api_mod, "_session_manager", _FakeSessionManager())
            monkeypatch.setattr(api_mod, "_save_user_profile", lambda *_args, **_kwargs: None)
            monkeypatch.setattr(api_mod, "_save_media_knowledge", lambda *_args, **_kwargs: None)
            monkeypatch.setattr(
                api_mod,
                "prepare_autonomous_incoming_message",
                lambda **_kwargs: PreparedMessage(
                    text="Привет",
                    media_used=False,
                    used_attachments=[],
                    skipped_attachments=[],
                    media_meta={},
                    media_turn_context=None,
                ),
            )

            req = api_mod.ProcessRequest(
                session_id="new-session",
                user_id="user-1",
                message=api_mod.MessagePayload(text="Привет"),
            )

            api_mod._process_message_request(req)

            assert captured["run_session_job_client_id"] == "user-1"
            assert captured["profile_data"]["company_name"] == "Альфа Логистик"
            assert captured["profile_data"]["business_type"] == "логистика"
            assert captured["media_cards"][0]["knowledge_id"] == "card-1"
        finally:
            api_mod.DB_PATH = original

    def test_load_snapshot_returns_none_for_missing(self, tmp_path, monkeypatch):
        """_load_snapshot for non-existent key must return None."""
        api_mod = _import_api_module_with_fastapi_stub(monkeypatch)

        db_path = str(tmp_path / "test_missing.db")
        original = api_mod.DB_PATH
        api_mod.DB_PATH = db_path
        try:
            api_mod._init_db()
            assert api_mod._load_snapshot("no-session", "no-user") is None
        finally:
            api_mod.DB_PATH = original


# ---------------------------------------------------------------------------
# BUG 1 tests: from_snapshot enable_tracing propagation
# ---------------------------------------------------------------------------

class TestFromSnapshotTracing:
    """Verify from_snapshot() properly propagates enable_tracing."""

    def test_from_snapshot_tracing_enabled(self, mock_llm):
        """from_snapshot(enable_tracing=True) must set _enable_decision_tracing=True."""
        from src.bot import SalesBot

        bot = SalesBot(llm=mock_llm, enable_tracing=True)
        snapshot = bot.to_snapshot()

        restored = SalesBot.from_snapshot(
            snapshot, llm=mock_llm, enable_tracing=True,
        )

        assert restored._enable_decision_tracing is True

    def test_from_snapshot_tracing_disabled_by_default(self, mock_llm):
        """from_snapshot() without enable_tracing must default to False."""
        from src.bot import SalesBot

        bot = SalesBot(llm=mock_llm)
        snapshot = bot.to_snapshot()

        restored = SalesBot.from_snapshot(snapshot, llm=mock_llm)

        assert restored._enable_decision_tracing is False

    def test_from_snapshot_tracing_produces_decision_trace(self, mock_llm):
        """
        With enable_tracing=True, bot.process() must include 'decision_trace'
        in the result — this is what api.py uses to compute kb_used.
        """
        from src.bot import SalesBot

        bot = SalesBot(llm=mock_llm, enable_tracing=True)
        snapshot = bot.to_snapshot()

        restored = SalesBot.from_snapshot(
            snapshot, llm=mock_llm, enable_tracing=True,
        )
        result = restored.process("Привет")

        # decision_trace must exist in result (may be empty but must be present)
        assert "decision_trace" in result, (
            "enable_tracing=True must produce 'decision_trace' in process() result"
        )

    def test_from_snapshot_no_tracing_no_decision_trace(self, mock_llm):
        """
        With enable_tracing=False (default), bot.process() must have
        decision_trace=None (no trace data collected).
        """
        from src.bot import SalesBot

        bot = SalesBot(llm=mock_llm)
        snapshot = bot.to_snapshot()

        restored = SalesBot.from_snapshot(snapshot, llm=mock_llm)
        result = restored.process("Привет")

        assert result.get("decision_trace") is None

    def test_original_constructor_tracing_still_works(self, mock_llm):
        """Sanity check: SalesBot(enable_tracing=True) sets the attribute."""
        from src.bot import SalesBot

        bot = SalesBot(llm=mock_llm, enable_tracing=True)
        assert bot._enable_decision_tracing is True

        bot2 = SalesBot(llm=mock_llm, enable_tracing=False)
        assert bot2._enable_decision_tracing is False
