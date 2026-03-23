"""Tests for active in-memory session runtime with delayed snapshot serialization."""

import asyncio
import importlib.machinery
import importlib.util
import sys
import types
from types import SimpleNamespace

import pytest
from src.media_preprocessor import PreparedMessage
from src.session_manager import SessionManager
from src.snapshot_buffer import LocalSnapshotBuffer


def _ensure_fastapi_stubs():
    if "fastapi" in sys.modules:
        return
    if importlib.util.find_spec("fastapi") is not None:
        return

    fastapi_mod = types.ModuleType("fastapi")
    fastapi_concurrency = types.ModuleType("fastapi.concurrency")
    fastapi_exceptions = types.ModuleType("fastapi.exceptions")
    fastapi_responses = types.ModuleType("fastapi.responses")
    fastapi_mod.__spec__ = importlib.machinery.ModuleSpec("fastapi", loader=None)
    fastapi_concurrency.__spec__ = importlib.machinery.ModuleSpec("fastapi.concurrency", loader=None)
    fastapi_exceptions.__spec__ = importlib.machinery.ModuleSpec("fastapi.exceptions", loader=None)
    fastapi_responses.__spec__ = importlib.machinery.ModuleSpec("fastapi.responses", loader=None)

    class _FastAPI:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def exception_handler(self, *_args, **_kwargs):
            def _decorator(fn):
                return fn
            return _decorator

        def post(self, *_args, **_kwargs):
            def _decorator(fn):
                return fn
            return _decorator

        def get(self, *_args, **_kwargs):
            def _decorator(fn):
                return fn
            return _decorator

    def _identity(*_args, **_kwargs):
        return None

    class _JSONResponse(dict):
        def __init__(self, *, status_code=None, content=None):
            super().__init__(status_code=status_code, content=content)

    class _RequestValidationError(Exception):
        def errors(self):
            return []

    async def _run_in_threadpool(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    fastapi_mod.Depends = _identity
    fastapi_mod.Header = _identity
    fastapi_mod.Request = object
    fastapi_mod.FastAPI = _FastAPI
    fastapi_concurrency.run_in_threadpool = _run_in_threadpool
    fastapi_exceptions.RequestValidationError = _RequestValidationError
    fastapi_responses.JSONResponse = _JSONResponse

    sys.modules.setdefault("fastapi", fastapi_mod)
    sys.modules.setdefault("fastapi.concurrency", fastapi_concurrency)
    sys.modules.setdefault("fastapi.exceptions", fastapi_exceptions)
    sys.modules.setdefault("fastapi.responses", fastapi_responses)


def _mk_manager(tmp_path, **kwargs):
    buffer = LocalSnapshotBuffer(db_path=str(tmp_path / "buffer.sqlite"))
    kwargs.setdefault("snapshot_buffer", buffer)
    return SessionManager(**kwargs), buffer


class TestSessionManagerActiveRuntime:
    def test_get_or_create_with_status_reports_cache_hit(self, mock_llm, tmp_path):
        manager, _ = _mk_manager(tmp_path)

        first = manager.get_or_create_with_status("s1", llm=mock_llm, client_id="c1")
        second = manager.get_or_create_with_status("s1", llm=mock_llm, client_id="c1")

        assert first.source == "new"
        assert second.source == "cache"
        assert second.bot is first.bot

    def test_serialize_inactive_final_sessions_after_one_hour(self, mock_llm, tmp_path):
        now = [1000.0]
        manager, buf = _mk_manager(tmp_path, now_provider=lambda: now[0])
        bot = manager.get_or_create("s1", llm=mock_llm, client_id="c1")

        bot.state_machine.state = "success"
        manager.touch("s1", client_id="c1", is_final=True)

        now[0] += 3599
        assert manager.serialize_inactive_final_sessions(3600) == 0
        assert buf.count() == 0

        now[0] += 1
        assert manager.serialize_inactive_final_sessions(3600) == 1
        assert buf.count() == 1

        restored = manager.get_or_create_with_status("s1", llm=mock_llm, client_id="c1")
        assert restored.source == "local_buffer"
        assert restored.bot.state_machine.state == "success"

    def test_touch_non_final_resets_final_since(self, mock_llm, tmp_path):
        now = [1000.0]
        manager, buf = _mk_manager(tmp_path, now_provider=lambda: now[0])
        bot = manager.get_or_create("s1", llm=mock_llm, client_id="c1")

        bot.state_machine.state = "success"
        manager.touch("s1", client_id="c1", is_final=True)
        now[0] += 10
        manager.touch("s1", client_id="c1", is_final=False)

        now[0] += 4000
        assert manager.serialize_inactive_final_sessions(3600) == 0
        assert buf.count() == 0
        cached = manager.get_or_create_with_status("s1", llm=mock_llm, client_id="c1")
        assert cached.source == "cache"
        assert cached.bot is bot

    def test_touch_handles_missing_session_and_none_final_flag(self, mock_llm, tmp_path):
        now = [1000.0]
        manager, _ = _mk_manager(tmp_path, now_provider=lambda: now[0])

        assert manager.touch("missing", client_id="c1", is_final=True) is False

        manager.get_or_create("s1", llm=mock_llm, client_id="c1")
        assert manager.touch("s1", client_id="c1", is_final=None) is True

    def test_close_all_sessions_serializes_cached_dialogs(self, mock_llm, tmp_path):
        manager, buf = _mk_manager(tmp_path)
        manager.get_or_create("s1", llm=mock_llm, client_id="c1")
        manager.get_or_create("s2", llm=mock_llm, client_id="c2")

        assert manager.close_all_sessions() == 2
        assert buf.count() == 2

    def test_save_skips_missing_entry_after_target_resolution(self, mock_llm, tmp_path):
        manager, buf = _mk_manager(tmp_path)
        manager.get_or_create("s1", llm=mock_llm, client_id="c1")

        class _VanishingSessions(dict):
            def get(self, key, default=None):
                return None

        manager._sessions = _VanishingSessions(manager._sessions)
        manager.save("s1", client_id="c1")

        assert buf.count() == 0

    def test_restore_uses_snapshot_history_tail_without_external_loader(self, mock_llm, tmp_path):
        now = [1000.0]
        manager, buf = _mk_manager(tmp_path, now_provider=lambda: now[0])
        bot = manager.get_or_create("s1", llm=mock_llm, client_id="c1")
        bot.history = [
            {"user": "u1", "bot": "b1"},
            {"user": "u2", "bot": "b2"},
            {"user": "u3", "bot": "b3"},
            {"user": "u4", "bot": "b4"},
            {"user": "u5", "bot": "b5"},
        ]
        bot.state_machine.state = "success"

        manager.touch("s1", client_id="c1", is_final=True)
        now[0] += 3600
        assert manager.serialize_inactive_final_sessions(3600) == 1

        restored = manager.get_or_create_with_status("s1", llm=mock_llm, client_id="c1")
        assert restored.source == "local_buffer"
        assert restored.bot.history == bot.history[-4:]


class _FakeApiBot:
    def __init__(self):
        self.process_calls = []
        self.hydrated = 0
        self.state_machine = SimpleNamespace(is_final=lambda: False)

    def process(self, text, *, media_turn_context=None):
        self.process_calls.append((text, media_turn_context))
        return {"response": f"echo:{text}", "decision_trace": None}

    def hydrate_external_memory(self, *, profile_data=None, media_cards=None):
        self.hydrated += 1


class _FakeApiManager:
    def __init__(self, bot, *, serialize_result=0, acquire_source_sequence=None):
        self.bot = bot
        self.serialize_result = serialize_result
        self.acquire_source_sequence = list(acquire_source_sequence or ["new", "cache"])
        self.calls = 0
        self.touches = []
        self.serialize_calls = []

    def serialize_inactive_final_sessions(self, idle_seconds):
        self.serialize_calls.append(idle_seconds)
        return self.serialize_result

    def get_or_create_with_status(self, *args, **kwargs):
        self.calls += 1
        source = (
            self.acquire_source_sequence[self.calls - 1]
            if self.calls <= len(self.acquire_source_sequence)
            else self.acquire_source_sequence[-1]
        )
        return SimpleNamespace(bot=self.bot, source=source)

    def touch(self, session_id, *, client_id=None, is_final=None):
        self.touches.append((session_id, client_id, is_final))
        return True


class _FakeConn:
    def __init__(self):
        self.committed = False
        self.closed = False

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


class _FakeSweeperEvent:
    def __init__(self, waits):
        self.waits = list(waits)
        self.set_called = False

    def wait(self, _timeout):
        if self.waits:
            return self.waits.pop(0)
        return True

    def set(self):
        self.set_called = True


class _FakeThread:
    def __init__(self, *, target=None, args=(), name=None, daemon=None):
        self.target = target
        self.args = args
        self.name = name
        self.daemon = daemon
        self.started = False
        self.join_timeout = None

    def start(self):
        self.started = True

    def join(self, timeout=None):
        self.join_timeout = timeout


class TestApiActiveRuntime:
    def test_storage_snapshot_helpers_split_and_delegate(self, monkeypatch):
        _ensure_fastapi_stubs()
        import src.api as api_mod

        saved = []
        monkeypatch.setattr(api_mod, "_load_snapshot", lambda sid, uid: {"sid": sid, "uid": uid})
        monkeypatch.setattr(api_mod, "_save_snapshot", lambda sid, uid, snapshot: saved.append((sid, uid, snapshot)))

        assert api_mod._split_storage_session_id("c1::s1") == ("s1", "c1")
        assert api_mod._split_storage_session_id("s1") == ("s1", "")
        assert api_mod._load_storage_snapshot("c1::s1") == {"sid": "s1", "uid": "c1"}

        api_mod._save_storage_snapshot("c1::s1", {"ok": True})
        assert saved == [("s1", "c1", {"ok": True})]

    def test_save_media_knowledge_persists_and_closes_connection(self, monkeypatch):
        _ensure_fastapi_stubs()
        import src.api as api_mod

        conn = _FakeConn()
        calls = []

        monkeypatch.setattr(api_mod, "_db_connect", lambda: conn)
        monkeypatch.setattr(api_mod, "_save_media_knowledge_conn", lambda *args, **kwargs: calls.append((args, kwargs)))
        monkeypatch.setattr(api_mod.time, "time", lambda: 123.0)

        api_mod._save_media_knowledge("s1", "u1", object())

        assert len(calls) == 1
        assert calls[0][1]["session_id"] == "s1"
        assert calls[0][1]["user_id"] == "u1"
        assert calls[0][1]["updated_at"] == 123.0
        assert conn.committed is True
        assert conn.closed is True

    def test_run_session_sweeper_handles_none_and_exceptional_manager(self, monkeypatch):
        _ensure_fastapi_stubs()
        import src.api as api_mod

        logs = []
        event = _FakeSweeperEvent([False, True])
        monkeypatch.setattr(api_mod, "_session_manager", None)
        monkeypatch.setattr(api_mod.logger, "exception", lambda message: logs.append(message))

        api_mod._run_session_sweeper(event)
        assert logs == []

        class _BrokenManager:
            def serialize_inactive_final_sessions(self, _idle_seconds):
                raise RuntimeError("boom")

        event = _FakeSweeperEvent([False, True])
        monkeypatch.setattr(api_mod, "_session_manager", _BrokenManager())
        api_mod._run_session_sweeper(event)
        assert logs == ["Session sweeper failed"]

    def test_run_session_sweeper_logs_when_sessions_serialized(self, monkeypatch):
        _ensure_fastapi_stubs()
        import src.api as api_mod

        manager = _FakeApiManager(_FakeApiBot(), serialize_result=2)
        infos = []
        event = _FakeSweeperEvent([False, True])

        monkeypatch.setattr(api_mod, "_session_manager", manager)
        monkeypatch.setattr(api_mod.logger, "info", lambda message, **kwargs: infos.append((message, kwargs)))

        api_mod._run_session_sweeper(event)

        assert manager.serialize_calls == [api_mod.ACTIVE_SESSION_FINAL_IDLE_SECONDS]
        assert infos == [
            (
                "Serialized inactive final sessions",
                {"count": 2, "idle_seconds": api_mod.ACTIVE_SESSION_FINAL_IDLE_SECONDS},
            )
        ]

    def test_lifespan_initializes_and_serializes_sessions_on_shutdown(self, monkeypatch):
        _ensure_fastapi_stubs()
        import src.api as api_mod

        thread_holder = {}
        event = _FakeSweeperEvent([])
        created_managers = []
        llm_obj = object()
        infos = []

        class _FakeManager:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.closed = 0
                created_managers.append(self)

            def close_all_sessions(self):
                self.closed += 1
                return 2

        def _make_thread(*, target=None, args=(), name=None, daemon=None):
            thread_holder["thread"] = _FakeThread(target=target, args=args, name=name, daemon=daemon)
            return thread_holder["thread"]

        monkeypatch.setattr(api_mod, "_setup_production_flags", lambda: None)
        monkeypatch.setattr(api_mod, "_init_db", lambda: None)
        monkeypatch.setattr(api_mod, "OllamaLLM", lambda: llm_obj)
        monkeypatch.setattr(api_mod, "SessionManager", _FakeManager)
        monkeypatch.setattr(api_mod, "_start_startup_warmup", lambda: None)
        monkeypatch.setattr(api_mod.threading, "Event", lambda: event)
        monkeypatch.setattr(api_mod.threading, "Thread", _make_thread)
        monkeypatch.setattr(api_mod.logger, "warning", lambda *args, **kwargs: None)
        monkeypatch.setattr(api_mod.logger, "info", lambda message, **kwargs: infos.append((message, kwargs)))
        monkeypatch.setattr(api_mod, "API_KEY", "secure")

        async def _run():
            async with api_mod.lifespan(object()):
                assert api_mod._llm is llm_obj
                assert api_mod._session_manager is created_managers[0]
                assert api_mod._session_sweeper_stop is event
                assert thread_holder["thread"].started is True

        asyncio.run(_run())

        assert created_managers[0].closed == 1
        assert event.set_called is True
        assert thread_holder["thread"].join_timeout == 2
        assert ("Serialized sessions on shutdown", {"count": 2}) in infos
        assert api_mod._llm is None
        assert api_mod._session_manager is None
        assert api_mod._session_sweeper_stop is None
        assert api_mod._session_sweeper_thread is None

    def test_lifespan_handles_shutdown_serialization_failure(self, monkeypatch):
        _ensure_fastapi_stubs()
        import src.api as api_mod

        event = _FakeSweeperEvent([])
        errors = []

        class _BrokenManager:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def close_all_sessions(self):
                raise RuntimeError("boom")

        monkeypatch.setattr(api_mod, "_setup_production_flags", lambda: None)
        monkeypatch.setattr(api_mod, "_init_db", lambda: None)
        monkeypatch.setattr(api_mod, "OllamaLLM", lambda: object())
        monkeypatch.setattr(api_mod, "SessionManager", _BrokenManager)
        monkeypatch.setattr(api_mod, "_start_startup_warmup", lambda: None)
        monkeypatch.setattr(api_mod.threading, "Event", lambda: event)
        monkeypatch.setattr(api_mod.threading, "Thread", lambda **kwargs: _FakeThread(**kwargs))
        monkeypatch.setattr(api_mod.logger, "warning", lambda *args, **kwargs: None)
        monkeypatch.setattr(api_mod.logger, "info", lambda *args, **kwargs: None)
        monkeypatch.setattr(api_mod.logger, "exception", lambda message: errors.append(message))
        monkeypatch.setattr(api_mod, "API_KEY", "secure")

        async def _run():
            async with api_mod.lifespan(object()):
                pass

        asyncio.run(_run())

        assert errors == ["Failed to serialize sessions on shutdown"]
        assert event.set_called is True
        assert api_mod._session_manager is None

    def test_process_request_raises_when_session_manager_is_unavailable(self, monkeypatch):
        _ensure_fastapi_stubs()
        import src.api as api_mod

        monkeypatch.setattr(api_mod, "_llm", object())
        monkeypatch.setattr(api_mod, "_session_manager", None)
        monkeypatch.setattr(
            api_mod,
            "prepare_autonomous_incoming_message",
            lambda **_kwargs: PreparedMessage(
                text="Здравствуйте",
                media_used=False,
                used_attachments=[],
                skipped_attachments=[],
                media_meta={},
                media_turn_context=None,
            ),
        )

        req = api_mod.ProcessRequest(
            session_id="BOT_6921_test",
            user_id="77710107606",
            message=api_mod.MessagePayload(text="Здравствуйте"),
        )

        with pytest.raises(api_mod.APIError, match="Session manager is not initialized"):
            api_mod._process_message_request(req)

    def test_process_request_uses_live_session_manager_and_skips_snapshot_roundtrip(self, monkeypatch):
        _ensure_fastapi_stubs()
        import src.api as api_mod

        bot = _FakeApiBot()
        manager = _FakeApiManager(bot)
        bootstrap_calls = []

        monkeypatch.setattr(api_mod, "_session_manager", manager)
        monkeypatch.setattr(api_mod, "_llm", object())
        monkeypatch.setattr(api_mod, "_load_snapshot", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("_load_snapshot should not be called")))
        monkeypatch.setattr(api_mod, "_persist_bot_state", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("_persist_bot_state should not be called")))
        monkeypatch.setattr(api_mod, "_bootstrap_bot_memory", lambda *_args, **_kwargs: bootstrap_calls.append(True))
        monkeypatch.setattr(api_mod, "_save_user_profile", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(api_mod, "_save_media_knowledge", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(
            api_mod,
            "prepare_autonomous_incoming_message",
            lambda **_kwargs: PreparedMessage(
                text="Здравствуйте",
                media_used=False,
                used_attachments=[],
                skipped_attachments=[],
                media_meta={},
                media_turn_context=None,
            ),
        )

        req = api_mod.ProcessRequest(
            session_id="BOT_6921_test",
            user_id="77710107606",
            message=api_mod.MessagePayload(text="Здравствуйте"),
        )

        result1 = api_mod._process_message_request(req)
        result2 = api_mod._process_message_request(req)

        assert result1["answer"] == "echo:Здравствуйте"
        assert result2["answer"] == "echo:Здравствуйте"
        assert manager.calls == 2
        assert len(bootstrap_calls) == 1
        assert len(bot.process_calls) == 2
        assert manager.touches == [
            ("BOT_6921_test", "77710107606", False),
            ("BOT_6921_test", "77710107606", False),
        ]

    def test_process_request_logs_request_path_serialization_and_skips_bootstrap_for_cache(self, monkeypatch):
        _ensure_fastapi_stubs()
        import src.api as api_mod

        bot = _FakeApiBot()
        manager = _FakeApiManager(
            bot,
            serialize_result=3,
            acquire_source_sequence=["cache"],
        )
        infos = []

        monkeypatch.setattr(api_mod, "_session_manager", manager)
        monkeypatch.setattr(api_mod, "_llm", object())
        monkeypatch.setattr(api_mod, "_bootstrap_bot_memory", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("bootstrap should not run for cache hit")))
        monkeypatch.setattr(api_mod, "_save_user_profile", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(api_mod, "_save_media_knowledge", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(api_mod.logger, "info", lambda message, **kwargs: infos.append((message, kwargs)))
        monkeypatch.setattr(
            api_mod,
            "prepare_autonomous_incoming_message",
            lambda **_kwargs: PreparedMessage(
                text="Здравствуйте",
                media_used=False,
                used_attachments=[],
                skipped_attachments=[],
                media_meta={},
                media_turn_context=None,
            ),
        )

        req = api_mod.ProcessRequest(
            session_id="BOT_6921_test",
            user_id="77710107606",
            message=api_mod.MessagePayload(text="Здравствуйте"),
        )

        result = api_mod._process_message_request(req)

        assert result["answer"] == "echo:Здравствуйте"
        assert manager.serialize_calls == [api_mod.ACTIVE_SESSION_FINAL_IDLE_SECONDS]
        assert infos == [
            (
                "Serialized inactive final sessions on request path",
                {"count": 3, "idle_seconds": api_mod.ACTIVE_SESSION_FINAL_IDLE_SECONDS},
            )
        ]
