"""Tests for SessionManager.close_session() — explicit dialog end trigger."""

import time

import pytest

from src.bot import SalesBot
from src.session_manager import SessionManager
from src.snapshot_buffer import LocalSnapshotBuffer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mk_manager(tmp_path, **kwargs):
    buffer = LocalSnapshotBuffer(db_path=str(tmp_path / "buffer.sqlite"))
    kwargs.setdefault("snapshot_buffer", buffer)
    return SessionManager(**kwargs), buffer


# ---------------------------------------------------------------------------
# Basic close_session behaviour
# ---------------------------------------------------------------------------


class TestCloseSessionBasic:
    def test_close_returns_true_when_session_exists(self, mock_llm, tmp_path):
        manager, buf = _mk_manager(tmp_path)
        manager.get_or_create("s1", llm=mock_llm, client_id="c1")

        assert manager.close_session("s1", client_id="c1") is True

    def test_close_returns_false_when_session_missing(self, mock_llm, tmp_path):
        manager, _ = _mk_manager(tmp_path)

        assert manager.close_session("no-such", client_id="c1") is False

    def test_close_enqueues_snapshot_to_buffer(self, mock_llm, tmp_path):
        manager, buf = _mk_manager(tmp_path)
        manager.get_or_create("s1", llm=mock_llm, client_id="c1")

        manager.close_session("s1", client_id="c1")
        assert buf.count() == 1

        snap = buf.get("s1", client_id="c1")
        assert snap is not None
        assert snap["client_id"] == "c1"
        assert snap["conversation_id"] == "s1"

    def test_close_removes_session_from_cache(self, mock_llm, tmp_path):
        manager, _ = _mk_manager(tmp_path)
        bot1 = manager.get_or_create("s1", llm=mock_llm, client_id="c1")
        manager.close_session("s1", client_id="c1")

        # Next get_or_create should create a new bot (not the same instance)
        bot2 = manager.get_or_create("s1", llm=mock_llm, client_id="c1")
        assert bot2 is not bot1

    def test_double_close_returns_false(self, mock_llm, tmp_path):
        manager, _ = _mk_manager(tmp_path)
        manager.get_or_create("s1", llm=mock_llm, client_id="c1")

        assert manager.close_session("s1", client_id="c1") is True
        assert manager.close_session("s1", client_id="c1") is False

    def test_close_requires_client_id_by_default(self, mock_llm, tmp_path):
        manager, _ = _mk_manager(tmp_path)
        manager.get_or_create("s1", llm=mock_llm, client_id="c1")

        with pytest.raises(ValueError, match="client_id is required"):
            manager.close_session("s1")

    def test_close_without_client_id_when_not_required(self, mock_llm, tmp_path):
        manager, buf = _mk_manager(tmp_path, require_client_id=False)
        manager.get_or_create("s1", llm=mock_llm)

        assert manager.close_session("s1") is True
        assert buf.count() == 1


# ---------------------------------------------------------------------------
# Snapshot content after close
# ---------------------------------------------------------------------------


class TestCloseSessionSnapshot:
    def test_snapshot_contains_compacted_history(self, mock_llm, tmp_path):
        manager, buf = _mk_manager(tmp_path)
        bot = manager.get_or_create("s1", llm=mock_llm, client_id="c1")
        # Feed enough history for compaction to have material
        for i in range(6):
            bot.history.append({"user": f"u{i}", "bot": f"b{i}"})

        manager.close_session("s1", client_id="c1")

        snap = buf.get("s1", client_id="c1")
        assert snap["history"] == []  # history always empty in snapshot
        assert snap.get("history_compact") is not None
        assert snap.get("history_compact_meta") is not None

    def test_snapshot_preserves_state_machine(self, mock_llm, tmp_path):
        manager, buf = _mk_manager(tmp_path)
        bot = manager.get_or_create("s1", llm=mock_llm, client_id="c1")
        bot.state_machine.state = "spin_problem"
        bot.state_machine.collected_data = {"company_size": "10"}

        manager.close_session("s1", client_id="c1")

        snap = buf.get("s1", client_id="c1")
        assert snap["state_machine"]["state"] == "spin_problem"
        assert snap["state_machine"]["collected_data"]["company_size"] == "10"

    def test_snapshot_preserves_guard(self, mock_llm, tmp_path):
        manager, buf = _mk_manager(tmp_path)
        bot = manager.get_or_create("s1", llm=mock_llm, client_id="c1")
        bot.guard.check("greeting", "привет", {})
        bot.guard.check("company_info", "у нас магазин", {})

        manager.close_session("s1", client_id="c1")

        snap = buf.get("s1", client_id="c1")
        assert snap["guard"]["turn_count"] == 2

    def test_snapshot_preserves_lead_score(self, mock_llm, tmp_path):
        manager, buf = _mk_manager(tmp_path)
        bot = manager.get_or_create("s1", llm=mock_llm, client_id="c1")
        bot.lead_scorer.add_signal("explicit_problem")
        bot.lead_scorer.end_turn()

        manager.close_session("s1", client_id="c1")

        snap = buf.get("s1", client_id="c1")
        assert snap["lead_scorer"]["current_score"] > 0


# ---------------------------------------------------------------------------
# Restore after close
# ---------------------------------------------------------------------------


class TestCloseAndRestore:
    def test_restore_from_local_buffer_after_close(self, mock_llm, tmp_path):
        external_history = {"s1": []}

        def load_history_tail(sid, n):
            return external_history.get(sid, [])[-n:]

        manager, buf = _mk_manager(tmp_path, load_history_tail=load_history_tail)
        bot = manager.get_or_create("s1", llm=mock_llm, client_id="c1")
        bot.state_machine.state = "spin_problem"
        bot.state_machine.collected_data = {"company_size": "50"}
        bot.history = [
            {"user": "Привет", "bot": "Здравствуйте!"},
            {"user": "У нас 50 человек", "bot": "Какие проблемы?"},
        ]
        external_history["s1"] = list(bot.history)

        manager.close_session("s1", client_id="c1")
        assert buf.count() == 1

        # Restore with fresh manager (same buffer)
        manager2, _ = _mk_manager.__wrapped__(tmp_path) if hasattr(_mk_manager, '__wrapped__') else (None, None)
        # Just use same manager — session was removed from cache
        restored = manager.get_or_create("s1", llm=mock_llm, client_id="c1")

        assert buf.count() == 0  # consumed from buffer
        assert restored.state_machine.state == "spin_problem"
        assert restored.state_machine.collected_data.get("company_size") == "50"
        assert restored.client_id == "c1"
        assert restored.history == external_history["s1"][-4:]

    def test_close_then_restore_via_external_snapshot(self, mock_llm, tmp_path):
        external_snapshots = {}
        external_history = {"s1": []}

        def save_snapshot(sid, snapshot):
            external_snapshots[sid] = snapshot

        def load_snapshot(sid):
            return external_snapshots.get(sid)

        def load_history_tail(sid, n):
            return external_history.get(sid, [])[-n:]

        buf = LocalSnapshotBuffer(db_path=str(tmp_path / "buffer.sqlite"))
        # Use dynamic time: start before flush_hour, switch after close
        current_time = [time.struct_time((2026, 2, 6, 20, 0, 0, 0, 0, -1))]

        manager = SessionManager(
            save_snapshot=save_snapshot,
            load_snapshot=load_snapshot,
            load_history_tail=load_history_tail,
            snapshot_buffer=buf,
            flush_hour=23,
            time_provider=lambda: current_time[0],
        )

        bot = manager.get_or_create("s1", llm=mock_llm, client_id="c1")
        bot.state_machine.state = "presentation"
        bot.history = [{"user": f"u{i}", "bot": f"b{i}"} for i in range(5)]
        external_history["s1"] = list(bot.history)

        manager.close_session("s1", client_id="c1")
        assert buf.count() == 1

        # Advance time past flush_hour — next get_or_create triggers batch flush
        current_time[0] = time.struct_time((2026, 2, 6, 23, 1, 0, 0, 0, -1))
        restored = manager.get_or_create("s1", llm=mock_llm, client_id="c1")

        # Snapshot should have been flushed to external
        assert "c1::s1" in external_snapshots
        assert restored.state_machine.state == "presentation"


# ---------------------------------------------------------------------------
# Multi-tenant isolation
# ---------------------------------------------------------------------------


class TestCloseSessionTenantIsolation:
    def test_close_only_affects_target_client(self, mock_llm, tmp_path):
        manager, buf = _mk_manager(tmp_path)
        bot_c1 = manager.get_or_create("shared", llm=mock_llm, client_id="c1")
        bot_c2 = manager.get_or_create("shared", llm=mock_llm, client_id="c2")

        manager.close_session("shared", client_id="c1")

        # c2 should still be in cache (same bot instance)
        bot_c2_again = manager.get_or_create("shared", llm=mock_llm, client_id="c2")
        assert bot_c2_again is bot_c2

        # c1 was closed — should get new bot
        bot_c1_new = manager.get_or_create("shared", llm=mock_llm, client_id="c1")
        assert bot_c1_new is not bot_c1

    def test_close_wrong_client_returns_false(self, mock_llm, tmp_path):
        manager, _ = _mk_manager(tmp_path)
        manager.get_or_create("s1", llm=mock_llm, client_id="c1")

        # Trying to close with wrong client_id
        assert manager.close_session("s1", client_id="wrong") is False

    def test_close_multiple_clients_independently(self, mock_llm, tmp_path):
        manager, buf = _mk_manager(tmp_path)

        for cid in ["c1", "c2", "c3"]:
            manager.get_or_create("s1", llm=mock_llm, client_id=cid)

        manager.close_session("s1", client_id="c2")
        assert buf.count() == 1

        manager.close_session("s1", client_id="c1")
        assert buf.count() == 2

        manager.close_session("s1", client_id="c3")
        assert buf.count() == 3


# ---------------------------------------------------------------------------
# Session stays in cache without TTL (no auto-expiry)
# ---------------------------------------------------------------------------


class TestNoAutoExpiry:
    def test_session_persists_in_cache_indefinitely(self, mock_llm, tmp_path):
        """Without TTL, sessions should stay in cache until explicit close."""
        manager, buf = _mk_manager(tmp_path)
        bot = manager.get_or_create("s1", llm=mock_llm, client_id="c1")

        # Simulate many sequential accesses (previously TTL would expire)
        for _ in range(10):
            same_bot = manager.get_or_create("s1", llm=mock_llm, client_id="c1")
            assert same_bot is bot

        # No snapshots created — session is still active
        assert buf.count() == 0

    def test_no_cleanup_expired_method(self):
        """cleanup_expired() should no longer exist."""
        assert not hasattr(SessionManager, "cleanup_expired")


# ---------------------------------------------------------------------------
# Integration: close after process()
# ---------------------------------------------------------------------------


class TestCloseAfterProcess:
    def test_close_after_bot_process(self, mock_llm, tmp_path):
        external_history = {"s1": []}

        def load_history_tail(sid, n):
            return external_history.get(sid, [])[-n:]

        manager, buf = _mk_manager(tmp_path, load_history_tail=load_history_tail)
        bot = manager.get_or_create("s1", llm=mock_llm, client_id="c1")

        result = bot.process("Привет")
        external_history["s1"].append(bot.history[-1])
        assert "response" in result

        result = bot.process("У нас магазин")
        external_history["s1"].append(bot.history[-1])

        # Server decides dialog is over
        closed = manager.close_session("s1", client_id="c1")
        assert closed is True
        assert buf.count() == 1

        # Restore and verify continuity
        restored = manager.get_or_create("s1", llm=mock_llm, client_id="c1")
        assert restored.client_id == "c1"
        assert restored.history == external_history["s1"][-4:]
        assert buf.count() == 0

    def test_close_multiple_sessions_sequentially(self, mock_llm, tmp_path):
        manager, buf = _mk_manager(tmp_path)

        sessions = [("s1", "c1"), ("s2", "c2"), ("s3", "c3")]
        bots = {}
        for sid, cid in sessions:
            bot = manager.get_or_create(sid, llm=mock_llm, client_id=cid)
            bot.process("Привет")
            bots[(sid, cid)] = bot

        # Close all
        for sid, cid in sessions:
            assert manager.close_session(sid, client_id=cid) is True

        assert buf.count() == 3

        # Verify each snapshot has correct client_id
        for sid, cid in sessions:
            snap = buf.get(sid, client_id=cid)
            assert snap is not None
            assert snap["client_id"] == cid


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestCloseSessionEdgeCases:
    def test_close_with_empty_history(self, mock_llm, tmp_path):
        """Close right after creation (no messages processed)."""
        manager, buf = _mk_manager(tmp_path)
        manager.get_or_create("s1", llm=mock_llm, client_id="c1")

        assert manager.close_session("s1", client_id="c1") is True
        assert buf.count() == 1

        snap = buf.get("s1", client_id="c1")
        assert snap["history"] == []

    def test_save_then_close(self, mock_llm, tmp_path):
        """Calling save() then close() should produce 1 snapshot (upsert)."""
        manager, buf = _mk_manager(tmp_path)
        bot = manager.get_or_create("s1", llm=mock_llm, client_id="c1")
        bot.process("Привет")

        manager.save("s1", client_id="c1")
        assert buf.count() == 1

        # close_session also calls save internally, then deletes from cache
        manager.close_session("s1", client_id="c1")
        # Buffer should still have 1 entry (upsert on same key)
        assert buf.count() == 1

    def test_get_or_create_after_close_creates_fresh_bot(self, mock_llm, tmp_path):
        """After close + buffer consumed, next access creates brand new bot."""
        manager, buf = _mk_manager(tmp_path)
        bot = manager.get_or_create("s1", llm=mock_llm, client_id="c1")
        bot.state_machine.state = "presentation"

        manager.close_session("s1", client_id="c1")

        # Consume from buffer (restore)
        restored = manager.get_or_create("s1", llm=mock_llm, client_id="c1")
        assert restored.state_machine.state == "presentation"

        # Close again
        manager.close_session("s1", client_id="c1")

        # Consume again
        restored2 = manager.get_or_create("s1", llm=mock_llm, client_id="c1")
        assert restored2.state_machine.state == "presentation"
