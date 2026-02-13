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
import tempfile
import threading
import time
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# BUG 2 tests: SQLite WAL mode
# ---------------------------------------------------------------------------

class TestInitDbWalMode:
    """Verify _init_db() sets WAL journal mode and creates tables."""

    def test_init_db_creates_tables(self, tmp_path):
        """_init_db() must create conversations and user_profiles tables."""
        import src.api as api_mod

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

    def test_init_db_sets_wal_mode(self, tmp_path):
        """_init_db() must set journal_mode=WAL for concurrent access."""
        import src.api as api_mod

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

    def test_concurrent_writes_succeed_with_wal(self, tmp_path):
        """Multiple threads writing simultaneously must not raise 'database is locked'."""
        import src.api as api_mod

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

    def test_snapshot_roundtrip(self, tmp_path):
        """_save_snapshot then _load_snapshot must return identical data."""
        import src.api as api_mod

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

    def test_load_snapshot_returns_none_for_missing(self, tmp_path):
        """_load_snapshot for non-existent key must return None."""
        import src.api as api_mod

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
