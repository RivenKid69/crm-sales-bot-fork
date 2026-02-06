"""E2E test: restore conversation after a week using snapshot + history tail."""

import time

from src.session_manager import SessionManager
from src.snapshot_buffer import LocalSnapshotBuffer


def test_restore_after_week_with_history_tail(mock_e2e_llm, tmp_path):
    session_id = "sess-week-later"
    client_id = "client-week-later"
    external_snapshots = {}
    external_history = {session_id: []}

    def save_snapshot(sid, snapshot):
        external_snapshots[sid] = snapshot

    def load_snapshot(sid):
        return external_snapshots.get(sid)

    def load_history_tail(sid, n):
        return external_history.get(sid, [])[-n:]

    buffer = LocalSnapshotBuffer(db_path=str(tmp_path / "snapshot_buffer.sqlite"))

    # Day 1: before 23:00, user active
    day1_time = time.struct_time((2026, 2, 5, 20, 0, 0, 0, 0, -1))
    manager_day1 = SessionManager(
        ttl_seconds=0,  # expire immediately on cleanup
        save_snapshot=save_snapshot,
        load_snapshot=load_snapshot,
        load_history_tail=load_history_tail,
        snapshot_buffer=buffer,
        flush_hour=23,
        time_provider=lambda: day1_time,
    )

    bot = manager_day1.get_or_create(session_id, llm=mock_e2e_llm, client_id=client_id)
    for msg in [
        "Привет",
        "У нас небольшой магазин",
        "Есть проблемы с учетом товаров",
        "Хотели бы демо",
        "Спасибо",
    ]:
        bot.process(msg)
        external_history[session_id].append(bot.history[-1])

    # Force TTL cleanup -> snapshot enqueued locally (no external flush yet)
    removed = manager_day1.cleanup_expired()
    assert removed == 1
    assert buffer.count() == 1
    assert session_id not in external_snapshots

    # Week later: first request after 23:00 triggers flush then restore
    week_later_time = time.struct_time((2026, 2, 12, 23, 5, 0, 0, 0, -1))
    manager_week = SessionManager(
        ttl_seconds=3600,
        save_snapshot=save_snapshot,
        load_snapshot=load_snapshot,
        load_history_tail=load_history_tail,
        snapshot_buffer=buffer,
        flush_hour=23,
        time_provider=lambda: week_later_time,
    )

    restored = manager_week.get_or_create(session_id, llm=mock_e2e_llm, client_id=client_id)
    assert f"{client_id}::{session_id}" in external_snapshots
    assert buffer.count() == 0
    assert restored.history == external_history[session_id][-4:]

    # Continue conversation after restore
    restored.process("Давайте продолжим")
    assert restored.history[-1]["user"] == "Давайте продолжим"
