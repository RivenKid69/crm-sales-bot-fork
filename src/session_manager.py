"""
Session Manager - caches active sessions and loads snapshots only on cache miss.

Snapshot loading happens only when session is not in memory.
Expired sessions are compacted and enqueued locally.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from src.bot import SalesBot
from src.logger import logger
from src.snapshot_buffer import LocalSnapshotBuffer
from src.session_lock import SessionLockManager


@dataclass
class SessionEntry:
    bot: SalesBot
    last_activity: float
    created_at: float


class SessionManager:
    def __init__(
        self,
        ttl_seconds: int = 3600,
        load_snapshot: Optional[Callable[[str], Optional[Dict]]] = None,
        save_snapshot: Optional[Callable[[str, Dict], None]] = None,
        load_history_tail: Optional[Callable[[str, int], List[Dict]]] = None,
        snapshot_buffer: Optional[LocalSnapshotBuffer] = None,
        flush_hour: int = 23,
        time_provider: Optional[Callable[[], time.struct_time]] = None,
        lock_manager: Optional[SessionLockManager] = None,
    ):
        self._sessions: Dict[str, SessionEntry] = {}
        self._ttl = ttl_seconds
        self._load_snapshot = load_snapshot
        self._save_snapshot = save_snapshot
        self._load_history_tail = load_history_tail
        self._buffer = snapshot_buffer or LocalSnapshotBuffer()
        self._flush_hour = flush_hour
        self._time_provider = time_provider or time.localtime
        self._lock = lock_manager or SessionLockManager()

    def _maybe_flush_batch(self) -> None:
        """Flush buffered snapshots after first request past flush_hour."""
        now = self._time_provider()
        today = (now.tm_year, now.tm_mon, now.tm_mday)

        if now.tm_hour < self._flush_hour:
            return

        if self._buffer.last_flush_date == today:
            return

        if not self._buffer.try_flush_lock():
            return

        try:
            if self._save_snapshot is None:
                return

            batch = self._buffer.get_all()
            if not batch:
                self._buffer.last_flush_date = today
                return

            for session_id, snapshot in batch.items():
                self._save_snapshot(session_id, snapshot)

            self._buffer.clear()
            self._buffer.last_flush_date = today
            logger.info("Snapshot batch flushed", count=len(batch))
        finally:
            self._buffer.release_flush_lock()

    def _snapshot_matches_client(self, snapshot: Dict, client_id: Optional[str]) -> bool:
        """Verify snapshot belongs to expected client_id (if provided)."""
        if client_id is None:
            return True
        snap_client_id = snapshot.get("client_id")
        return snap_client_id == client_id

    def _override_snapshot_flow_config(
        self,
        snapshot: Dict,
        flow_name: Optional[str],
        config_name: Optional[str],
    ) -> Dict:
        """Override snapshot flow/config if external profile specifies different values."""
        if not snapshot:
            return snapshot
        updated = dict(snapshot)
        if flow_name and flow_name != snapshot.get("flow_name"):
            updated["flow_name"] = flow_name
        if config_name and config_name != snapshot.get("config_name"):
            updated["config_name"] = config_name
        return updated

    def get_or_create(
        self,
        session_id: str,
        llm=None,
        client_id: Optional[str] = None,
        flow_name: Optional[str] = None,
        config_name: Optional[str] = None,
    ) -> SalesBot:
        """
        Flow:
        1. First request after flush_hour triggers batch flush.
        2. Cache hit -> return.
        3. Expired -> snapshot + compaction -> local buffer.
        4. Local buffer -> restore (and delete on success).
        5. External snapshot -> restore.
        6. Otherwise -> new bot.
        """
        with self._lock.lock(session_id):
            self._maybe_flush_batch()
            now = time.time()

            # 1. Cache
            if session_id in self._sessions:
                entry = self._sessions[session_id]
                if now - entry.last_activity < self._ttl:
                    # Optional live switch of flow/config for active session
                    if flow_name or config_name:
                        current_flow = getattr(entry.bot, "_flow", None)
                        current_flow_name = current_flow.name if current_flow else None
                        current_config_name = getattr(getattr(entry.bot, "_config", None), "name", None)
                        if (flow_name and flow_name != current_flow_name) or (
                            config_name and config_name != current_config_name
                        ):
                            logger.info(
                                "Flow/config switch requested for active session",
                                session_id=session_id,
                                from_flow=current_flow_name,
                                to_flow=flow_name,
                                from_config=current_config_name,
                                to_config=config_name,
                            )
                            history_tail = entry.bot.history[-4:] if entry.bot.history else []
                            snapshot = entry.bot.to_snapshot(compact_history=False, history_tail_size=4)
                            snapshot = self._override_snapshot_flow_config(
                                snapshot, flow_name=flow_name, config_name=config_name
                            )
                            entry.bot = SalesBot.from_snapshot(
                                snapshot, llm=llm, history_tail=history_tail
                            )
                    entry.last_activity = now
                    logger.debug("Session from cache", session_id=session_id)
                    return entry.bot
                self.save(session_id)
                del self._sessions[session_id]

            # 2. Local buffer
            bot = None
            local_snapshot = self._buffer.get(session_id)
            if local_snapshot:
                if self._snapshot_matches_client(local_snapshot, client_id):
                    history_tail = (
                        self._load_history_tail(session_id, 4)
                        if self._load_history_tail
                        else []
                    )
                    try:
                        local_snapshot = self._override_snapshot_flow_config(
                            local_snapshot, flow_name=flow_name, config_name=config_name
                        )
                        bot = SalesBot.from_snapshot(local_snapshot, llm=llm, history_tail=history_tail)
                        self._buffer.delete(session_id)
                        logger.info("Session restored from local snapshot buffer", session_id=session_id)
                    except Exception:
                        logger.exception("Failed to restore from local snapshot buffer")
                else:
                    logger.warning(
                        "Snapshot client_id mismatch (local buffer)",
                        session_id=session_id,
                        expected_client_id=client_id,
                        snapshot_client_id=local_snapshot.get("client_id"),
                    )

            # 3. External snapshot
            if bot is None and self._load_snapshot:
                snapshot = self._load_snapshot(session_id)
                if snapshot and self._snapshot_matches_client(snapshot, client_id):
                    history_tail = (
                        self._load_history_tail(session_id, 4)
                        if self._load_history_tail
                        else []
                    )
                    snapshot = self._override_snapshot_flow_config(
                        snapshot, flow_name=flow_name, config_name=config_name
                    )
                    bot = SalesBot.from_snapshot(snapshot, llm=llm, history_tail=history_tail)
                    logger.info("Session restored from external snapshot", session_id=session_id)
                elif snapshot:
                    logger.warning(
                        "Snapshot client_id mismatch (external)",
                        session_id=session_id,
                        expected_client_id=client_id,
                        snapshot_client_id=snapshot.get("client_id"),
                    )

            # 4. New
            if bot is None:
                bot = SalesBot(llm=llm, flow_name=flow_name, client_id=client_id)
                bot.conversation_id = session_id
                if config_name and hasattr(bot._config_loader, "load_named"):
                    bot._config = bot._config_loader.load_named(config_name)
                logger.info("New session created", session_id=session_id)

            self._sessions[session_id] = SessionEntry(
                bot=bot,
                last_activity=now,
                created_at=now,
            )
            return bot

    def save(self, session_id: str) -> None:
        """Save session snapshot to local buffer (with compaction)."""
        if session_id not in self._sessions:
            return
        bot = self._sessions[session_id].bot
        snapshot = bot.to_snapshot(compact_history=True, history_tail_size=4)
        self._buffer.enqueue(session_id, snapshot)
        logger.debug("Snapshot enqueued locally", session_id=session_id)

    def cleanup_expired(self) -> int:
        """Remove expired sessions from cache."""
        now = time.time()
        expired = [
            sid for sid, entry in self._sessions.items()
            if now - entry.last_activity >= self._ttl
        ]
        for sid in expired:
            self.save(sid)
            del self._sessions[sid]

        if expired:
            logger.info("Cleaned up expired sessions", count=len(expired))
        return len(expired)
