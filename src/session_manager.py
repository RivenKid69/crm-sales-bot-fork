"""
Session Manager - caches active sessions and loads snapshots only on cache miss.

Snapshot loading happens only when session is not in memory.
Sessions are closed explicitly via close_session() call from the server.
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.bot import SalesBot
from src.logger import logger
from src.snapshot_buffer import LocalSnapshotBuffer
from src.session_lock import SessionLockManager


@dataclass
class SessionEntry:
    bot: SalesBot
    last_activity: float
    created_at: float
    final_since: Optional[float] = None


@dataclass(frozen=True)
class SessionAcquireResult:
    bot: SalesBot
    source: str


class SessionManager:
    STORAGE_KEY_SEPARATOR = "::"

    def __init__(
        self,
        load_snapshot: Optional[Callable[[str], Optional[Dict]]] = None,
        save_snapshot: Optional[Callable[[str, Dict], None]] = None,
        load_history_tail: Optional[Callable[[str, int], List[Dict]]] = None,
        snapshot_buffer: Optional[LocalSnapshotBuffer] = None,
        flush_hour: int = 23,
        time_provider: Optional[Callable[[], time.struct_time]] = None,
        lock_manager: Optional[SessionLockManager] = None,
        require_client_id: bool = True,
        now_provider: Optional[Callable[[], float]] = None,
    ):
        self._sessions: Dict[Tuple[str, str], SessionEntry] = {}
        self._load_snapshot = load_snapshot
        self._save_snapshot = save_snapshot
        self._load_history_tail = load_history_tail
        self._buffer = snapshot_buffer or LocalSnapshotBuffer()
        self._flush_hour = flush_hour
        self._time_provider = time_provider or time.localtime
        self._now = now_provider or time.time
        self._lock = lock_manager or SessionLockManager()
        self._require_client_id = require_client_id
        self._cache_lock = threading.RLock()

    def _normalize_client_id(self, client_id: Optional[str]) -> str:
        if client_id is None:
            return ""
        return str(client_id).strip()

    def _ensure_client_id(self, client_id: Optional[str], session_id: str) -> None:
        if self._require_client_id and not self._normalize_client_id(client_id):
            raise ValueError(
                f"client_id is required for session '{session_id}' "
                "to guarantee tenant isolation"
            )

    def _cache_key(self, session_id: str, client_id: Optional[str]) -> Tuple[str, str]:
        return (self._normalize_client_id(client_id), session_id)

    def _storage_session_id(self, session_id: str, client_id: Optional[str]) -> str:
        norm_client_id = self._normalize_client_id(client_id)
        if norm_client_id:
            return f"{norm_client_id}{self.STORAGE_KEY_SEPARATOR}{session_id}"
        return session_id

    def _session_lock_key(self, session_id: str, client_id: Optional[str]) -> str:
        return self._storage_session_id(session_id, client_id)

    def _load_external_snapshot_candidates(
        self,
        session_id: str,
        client_id: Optional[str],
    ) -> List[str]:
        """
        Build external storage IDs to try.

        First try tenant-aware key, then legacy key for backward compatibility.
        """
        norm_client_id = self._normalize_client_id(client_id)
        candidates = [self._storage_session_id(session_id, norm_client_id or None)]
        if norm_client_id:
            candidates.append(session_id)
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for sid in candidates:
            if sid not in seen:
                seen.add(sid)
                unique.append(sid)
        return unique

    def _maybe_flush_batch(self, *, force: bool = False) -> int:
        """Flush buffered snapshots after first request past flush_hour."""
        now = self._time_provider()
        today = (now.tm_year, now.tm_mon, now.tm_mday)

        if not force and now.tm_hour < self._flush_hour:
            return 0

        if not force and self._buffer.last_flush_date == today:
            return 0

        if not self._buffer.try_flush_lock():
            return 0

        try:
            if self._save_snapshot is None:
                return 0

            entries = self._buffer.get_all_entries()
            if not entries:
                if not force:
                    self._buffer.last_flush_date = today
                return 0

            for entry in entries:
                client_id = entry.get("client_id")
                session_id = entry["session_id"]
                snapshot = entry["snapshot"]
                storage_session_id = self._storage_session_id(session_id, client_id)
                self._save_snapshot(storage_session_id, snapshot)

            self._buffer.clear()
            self._buffer.last_flush_date = today
            logger.info("Snapshot batch flushed", count=len(entries))
            return len(entries)
        finally:
            self._buffer.release_flush_lock()

    def flush_buffered_snapshots(self, *, force: bool = True) -> int:
        """Persist locally buffered snapshots to external storage when available."""
        return self._maybe_flush_batch(force=force)

    def run_session_job(
        self,
        session_id: str,
        *,
        client_id: Optional[str] = None,
        job: Callable[[], Any],
    ) -> Any:
        """Run a full session-scoped job under the per-session lock."""
        self._ensure_client_id(client_id, session_id)
        normalized_client_id = self._normalize_client_id(client_id) or None
        lock_key = self._session_lock_key(session_id, normalized_client_id)
        with self._lock.lock(lock_key):
            return job()

    def _snapshot_matches_client(self, snapshot: Dict, client_id: Optional[str]) -> bool:
        """Verify snapshot belongs to expected client_id (if provided)."""
        expected_client = self._normalize_client_id(client_id)
        actual_client = self._normalize_client_id(snapshot.get("client_id"))

        if not expected_client:
            if self._require_client_id:
                return False
            return True
        return actual_client == expected_client

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

    def _restore_from_snapshot(
        self,
        snapshot: Dict,
        session_id: str,
        client_id: Optional[str] = None,
        llm=None,
        flow_name: Optional[str] = None,
        config_name: Optional[str] = None,
        enable_tracing: bool = False,
    ) -> SalesBot:
        history_tail = None
        if self._load_history_tail:
            loaded_tail = self._load_history_tail(session_id, 4)
            if loaded_tail:
                history_tail = loaded_tail
        snapshot = self._override_snapshot_flow_config(
            snapshot, flow_name=flow_name, config_name=config_name
        )
        return SalesBot.from_snapshot(
            snapshot,
            llm=llm,
            history_tail=history_tail,
            enable_tracing=enable_tracing,
        )

    def _get_or_create_with_status_locked(
        self,
        session_id: str,
        llm=None,
        client_id: Optional[str] = None,
        flow_name: Optional[str] = None,
        config_name: Optional[str] = None,
        enable_tracing: bool = False,
    ) -> SessionAcquireResult:
        """
        Same as get_or_create(), but also returns the source of the session.

        source:
        - cache
        - local_buffer
        - external_snapshot
        - new
        """
        normalized_client_id = self._normalize_client_id(client_id) or None
        cache_key = self._cache_key(session_id, normalized_client_id)
        self._maybe_flush_batch()
        now = self._now()

        with self._cache_lock:
            entry = self._sessions.get(cache_key)
        if entry is not None:
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
            logger.debug(
                "Session from cache",
                session_id=session_id,
                client_id=normalized_client_id,
            )
            return SessionAcquireResult(bot=entry.bot, source="cache")

        bot = None
        source = "new"
        local_snapshot = self._buffer.get(session_id, client_id=normalized_client_id)
        if local_snapshot:
            if self._snapshot_matches_client(local_snapshot, client_id):
                try:
                    bot = self._restore_from_snapshot(
                        local_snapshot,
                        session_id=session_id,
                        client_id=normalized_client_id,
                        llm=llm,
                        flow_name=flow_name,
                        config_name=config_name,
                        enable_tracing=enable_tracing,
                    )
                    self._buffer.delete(session_id, client_id=normalized_client_id)
                    source = "local_buffer"
                    logger.info(
                        "Session restored from local snapshot buffer",
                        session_id=session_id,
                        client_id=normalized_client_id,
                    )
                except Exception:
                    logger.exception("Failed to restore from local snapshot buffer")
            else:
                logger.warning(
                    "Snapshot client_id mismatch (local buffer)",
                    session_id=session_id,
                    expected_client_id=normalized_client_id,
                    snapshot_client_id=local_snapshot.get("client_id"),
                )

        if bot is None and self._load_snapshot:
            for external_session_id in self._load_external_snapshot_candidates(
                session_id=session_id,
                client_id=normalized_client_id,
            ):
                snapshot = self._load_snapshot(external_session_id)
                if not snapshot:
                    continue
                if self._snapshot_matches_client(snapshot, client_id):
                    bot = self._restore_from_snapshot(
                        snapshot,
                        session_id=session_id,
                        client_id=normalized_client_id,
                        llm=llm,
                        flow_name=flow_name,
                        config_name=config_name,
                        enable_tracing=enable_tracing,
                    )
                    source = "external_snapshot"
                    logger.info(
                        "Session restored from external snapshot",
                        session_id=session_id,
                        client_id=normalized_client_id,
                        storage_session_id=external_session_id,
                    )
                    break

                logger.warning(
                    "Snapshot client_id mismatch (external)",
                    session_id=session_id,
                    expected_client_id=normalized_client_id,
                    snapshot_client_id=snapshot.get("client_id"),
                    storage_session_id=external_session_id,
                )

        if bot is None:
            bot = SalesBot(
                llm=llm,
                flow_name=flow_name,
                client_id=normalized_client_id,
                config_name=config_name,
                enable_tracing=enable_tracing,
            )
            bot.conversation_id = session_id
            logger.info(
                "New session created",
                session_id=session_id,
                client_id=normalized_client_id,
            )

        entry = SessionEntry(
            bot=bot,
            last_activity=now,
            created_at=now,
            final_since=now if bot.state_machine.is_final() else None,
        )
        with self._cache_lock:
            self._sessions[cache_key] = entry
        return SessionAcquireResult(bot=bot, source=source)

    def get_or_create_with_status(
        self,
        session_id: str,
        llm=None,
        client_id: Optional[str] = None,
        flow_name: Optional[str] = None,
        config_name: Optional[str] = None,
        enable_tracing: bool = False,
        *,
        assume_locked: bool = False,
    ) -> SessionAcquireResult:
        """
        Same as get_or_create(), but also returns the source of the session.

        source:
        - cache
        - local_buffer
        - external_snapshot
        - new
        """
        self._ensure_client_id(client_id, session_id)
        normalized_client_id = self._normalize_client_id(client_id) or None
        if assume_locked:
            return self._get_or_create_with_status_locked(
                session_id=session_id,
                llm=llm,
                client_id=normalized_client_id,
                flow_name=flow_name,
                config_name=config_name,
                enable_tracing=enable_tracing,
            )

        lock_key = self._session_lock_key(session_id, normalized_client_id)
        with self._lock.lock(lock_key):
            return self._get_or_create_with_status_locked(
                session_id=session_id,
                llm=llm,
                client_id=normalized_client_id,
                flow_name=flow_name,
                config_name=config_name,
                enable_tracing=enable_tracing,
            )

    def get_or_create(
        self,
        session_id: str,
        llm=None,
        client_id: Optional[str] = None,
        flow_name: Optional[str] = None,
        config_name: Optional[str] = None,
        enable_tracing: bool = False,
    ) -> SalesBot:
        """
        Flow:
        1. First request after flush_hour triggers batch flush.
        2. Cache hit -> return.
        3. Local buffer -> restore (and delete on success).
        4. External snapshot -> restore.
        5. Otherwise -> new bot.
        """
        return self.get_or_create_with_status(
            session_id=session_id,
            llm=llm,
            client_id=client_id,
            flow_name=flow_name,
            config_name=config_name,
            enable_tracing=enable_tracing,
        ).bot

    def touch(
        self,
        session_id: str,
        *,
        client_id: Optional[str] = None,
        is_final: Optional[bool] = None,
    ) -> bool:
        """Update last_activity and optional final-state timing for a cached session."""
        self._ensure_client_id(client_id, session_id)
        normalized_client_id = self._normalize_client_id(client_id) or None
        cache_key = self._cache_key(session_id, normalized_client_id)
        now = self._now()
        with self._cache_lock:
            entry = self._sessions.get(cache_key)
            if entry is None:
                return False
            entry.last_activity = now
            if is_final is None:
                return True
            if is_final:
                entry.final_since = entry.final_since or now
            else:
                entry.final_since = None
            return True

    def serialize_inactive_final_sessions(self, max_idle_seconds: float) -> int:
        """
        Serialize and remove sessions that have stayed in a final state longer
        than max_idle_seconds.
        """
        cutoff = self._now() - float(max_idle_seconds)
        with self._cache_lock:
            targets = [
                (client_id, session_id)
                for (client_id, session_id), entry in self._sessions.items()
                if entry.final_since is not None and entry.final_since <= cutoff
            ]

        serialized = 0
        for client_id, session_id in targets:
            if self.close_session(
                session_id,
                client_id=client_id or None,
                durable=True,
                require_final_since_at_or_before=cutoff,
            ):
                serialized += 1
        return serialized

    def close_all_sessions(self, *, durable: bool = True) -> int:
        """Serialize and remove all cached sessions."""
        with self._cache_lock:
            targets = list(self._sessions.keys())

        closed = 0
        for client_id, session_id in targets:
            if self.close_session(
                session_id,
                client_id=client_id or None,
                durable=durable,
            ):
                closed += 1
        return closed

    def save(self, session_id: str, client_id: Optional[str] = None) -> None:
        """Save session snapshot to local buffer (with compaction)."""
        target_keys: List[Tuple[str, str]] = []
        norm_client_id = self._normalize_client_id(client_id)
        if client_id is not None:
            key = self._cache_key(session_id, norm_client_id or None)
            with self._cache_lock:
                exists = key in self._sessions
            if exists:
                target_keys.append(key)
        else:
            with self._cache_lock:
                target_keys = [key for key in self._sessions.keys() if key[1] == session_id]

        for key in target_keys:
            cached_client_id, cached_session_id = key
            with self._cache_lock:
                entry = self._sessions.get(key)
            if entry is None:
                continue
            bot = entry.bot
            snapshot = bot.to_snapshot(compact_history=True, history_tail_size=4)
            self._buffer.enqueue(
                cached_session_id,
                snapshot,
                client_id=cached_client_id or None,
            )
            logger.debug(
                "Snapshot enqueued locally",
                session_id=cached_session_id,
                client_id=cached_client_id or None,
            )

    def _persist_snapshot(
        self,
        session_id: str,
        *,
        client_id: Optional[str],
        snapshot: Dict[str, Any],
        durable: bool,
    ) -> str:
        if durable and self._save_snapshot is not None:
            storage_session_id = self._storage_session_id(session_id, client_id)
            self._save_snapshot(storage_session_id, snapshot)
            self._buffer.delete(session_id, client_id=client_id)
            return "external_snapshot"

        self._buffer.enqueue(
            session_id,
            snapshot,
            client_id=client_id,
        )
        return "local_buffer"

    def _close_session_locked(
        self,
        session_id: str,
        *,
        client_id: Optional[str],
        durable: bool,
        require_final_since_at_or_before: Optional[float],
    ) -> bool:
        cache_key = self._cache_key(session_id, client_id)
        with self._cache_lock:
            entry = self._sessions.get(cache_key)
        if entry is None:
            logger.warning(
                "close_session: session not found in cache",
                session_id=session_id,
                client_id=client_id,
            )
            return False

        if require_final_since_at_or_before is not None:
            final_since = entry.final_since
            if final_since is None or final_since > require_final_since_at_or_before:
                logger.debug(
                    "close_session skipped: session is no longer idle-final",
                    session_id=session_id,
                    client_id=client_id,
                    final_since=final_since,
                    cutoff=require_final_since_at_or_before,
                )
                return False

        snapshot = entry.bot.to_snapshot(compact_history=True, history_tail_size=4)
        persisted_via = self._persist_snapshot(
            session_id,
            client_id=client_id,
            snapshot=snapshot,
            durable=durable,
        )
        with self._cache_lock:
            self._sessions.pop(cache_key, None)
        logger.info(
            "Session closed and snapshot created",
            session_id=session_id,
            client_id=client_id,
            persisted_via=persisted_via,
            durable=durable,
        )
        return True

    def close_session(
        self,
        session_id: str,
        client_id: Optional[str] = None,
        *,
        durable: bool = False,
        require_final_since_at_or_before: Optional[float] = None,
    ) -> bool:
        """
        Close session explicitly: create snapshot with compaction and remove from cache.

        Called by external server when dialog ends.
        Returns True if session was found and closed, False otherwise.
        """
        self._ensure_client_id(client_id, session_id)
        normalized_client_id = self._normalize_client_id(client_id) or None
        lock_key = self._session_lock_key(session_id, normalized_client_id)

        with self._lock.lock(lock_key):
            return self._close_session_locked(
                session_id=session_id,
                client_id=normalized_client_id,
                durable=durable,
                require_final_since_at_or_before=require_final_since_at_or_before,
            )
