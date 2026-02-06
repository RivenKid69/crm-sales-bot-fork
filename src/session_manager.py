"""
Session Manager - caches active sessions and loads snapshots only on cache miss.

Snapshot loading happens only when session is not in memory.
Expired sessions are compacted and enqueued locally.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

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
    STORAGE_KEY_SEPARATOR = "::"

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
        require_client_id: bool = True,
    ):
        self._sessions: Dict[Tuple[str, str], SessionEntry] = {}
        self._ttl = ttl_seconds
        self._load_snapshot = load_snapshot
        self._save_snapshot = save_snapshot
        self._load_history_tail = load_history_tail
        self._buffer = snapshot_buffer or LocalSnapshotBuffer()
        self._flush_hour = flush_hour
        self._time_provider = time_provider or time.localtime
        self._lock = lock_manager or SessionLockManager()
        self._require_client_id = require_client_id

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

            entries = self._buffer.get_all_entries()
            if not entries:
                self._buffer.last_flush_date = today
                return

            for entry in entries:
                client_id = entry.get("client_id")
                session_id = entry["session_id"]
                snapshot = entry["snapshot"]
                storage_session_id = self._storage_session_id(session_id, client_id)
                self._save_snapshot(storage_session_id, snapshot)

            self._buffer.clear()
            self._buffer.last_flush_date = today
            logger.info("Snapshot batch flushed", count=len(entries))
        finally:
            self._buffer.release_flush_lock()

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
        llm=None,
        flow_name: Optional[str] = None,
        config_name: Optional[str] = None,
    ) -> SalesBot:
        history_tail = (
            self._load_history_tail(session_id, 4)
            if self._load_history_tail
            else []
        )
        snapshot = self._override_snapshot_flow_config(
            snapshot, flow_name=flow_name, config_name=config_name
        )
        return SalesBot.from_snapshot(snapshot, llm=llm, history_tail=history_tail)

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
        self._ensure_client_id(client_id, session_id)
        normalized_client_id = self._normalize_client_id(client_id) or None
        cache_key = self._cache_key(session_id, normalized_client_id)
        lock_key = self._storage_session_id(session_id, normalized_client_id)

        with self._lock.lock(lock_key):
            self._maybe_flush_batch()
            now = time.time()

            # 1. Cache
            if cache_key in self._sessions:
                entry = self._sessions[cache_key]
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
                    logger.debug(
                        "Session from cache",
                        session_id=session_id,
                        client_id=normalized_client_id,
                    )
                    return entry.bot
                self.save(session_id, client_id=normalized_client_id)
                del self._sessions[cache_key]

            # 2. Local buffer
            bot = None
            local_snapshot = self._buffer.get(session_id, client_id=normalized_client_id)
            if local_snapshot:
                if self._snapshot_matches_client(local_snapshot, client_id):
                    try:
                        bot = self._restore_from_snapshot(
                            local_snapshot,
                            session_id=session_id,
                            llm=llm,
                            flow_name=flow_name,
                            config_name=config_name,
                        )
                        self._buffer.delete(session_id, client_id=normalized_client_id)
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

            # 3. External snapshot
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
                            llm=llm,
                            flow_name=flow_name,
                            config_name=config_name,
                        )
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

            # 4. New
            if bot is None:
                bot = SalesBot(
                    llm=llm,
                    flow_name=flow_name,
                    client_id=normalized_client_id,
                    config_name=config_name,
                )
                bot.conversation_id = session_id
                logger.info(
                    "New session created",
                    session_id=session_id,
                    client_id=normalized_client_id,
                )

            self._sessions[cache_key] = SessionEntry(
                bot=bot,
                last_activity=now,
                created_at=now,
            )
            return bot

    def save(self, session_id: str, client_id: Optional[str] = None) -> None:
        """Save session snapshot to local buffer (with compaction)."""
        target_keys: List[Tuple[str, str]] = []
        norm_client_id = self._normalize_client_id(client_id)
        if client_id is not None:
            key = self._cache_key(session_id, norm_client_id or None)
            if key in self._sessions:
                target_keys.append(key)
        else:
            target_keys = [key for key in self._sessions.keys() if key[1] == session_id]

        for key in target_keys:
            cached_client_id, cached_session_id = key
            bot = self._sessions[key].bot
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

    def cleanup_expired(self) -> int:
        """Remove expired sessions from cache."""
        now = time.time()
        expired = [
            key for key, entry in self._sessions.items()
            if now - entry.last_activity >= self._ttl
        ]
        for client_key, sid in expired:
            self.save(sid, client_id=client_key or None)
            del self._sessions[(client_key, sid)]

        if expired:
            logger.info("Cleaned up expired sessions", count=len(expired))
        return len(expired)
