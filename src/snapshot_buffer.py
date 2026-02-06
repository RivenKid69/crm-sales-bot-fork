"""
LocalSnapshotBuffer - persistent local buffer for snapshots.

Uses SQLite for multi-process safety and durability.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.logger import logger


class LocalSnapshotBuffer:
    """Persistent snapshot buffer shared across processes."""

    DEFAULT_DB_NAME = "snapshot_buffer.sqlite"
    LOCK_NAME = "snapshot_batch_flush"
    STORAGE_KEY_SEPARATOR = "::"

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = Path(
            db_path or os.getenv("SNAPSHOT_BUFFER_PATH", self.DEFAULT_DB_NAME)
        ).resolve()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    @staticmethod
    def _normalize_client_id(client_id: Optional[str]) -> str:
        if client_id is None:
            return ""
        normalized = str(client_id).strip()
        return normalized

    def _storage_key(self, session_id: str, client_id: Optional[str]) -> str:
        norm_client_id = self._normalize_client_id(client_id)
        if norm_client_id:
            return f"{norm_client_id}{self.STORAGE_KEY_SEPARATOR}{session_id}"
        return session_id

    def _create_snapshots_table(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                client_id TEXT NOT NULL DEFAULT '',
                session_id TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY (client_id, session_id)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_snapshots_session_id
            ON snapshots(session_id)
            """
        )

    def _snapshots_table_exists(self, conn: sqlite3.Connection) -> bool:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='snapshots'"
        ).fetchone()
        return row is not None

    def _snapshots_has_client_id_column(self, conn: sqlite3.Connection) -> bool:
        columns = conn.execute("PRAGMA table_info(snapshots)").fetchall()
        return any(col[1] == "client_id" for col in columns)

    def _migrate_legacy_snapshots_table(self, conn: sqlite3.Connection) -> None:
        """Migrate legacy snapshots(session_id PK, ...) to tenant-aware schema."""
        logger.info("Migrating snapshot buffer schema to tenant-aware format")
        conn.execute(
            """
            CREATE TABLE snapshots_v2 (
                client_id TEXT NOT NULL DEFAULT '',
                session_id TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY (client_id, session_id)
            )
            """
        )

        rows = conn.execute(
            "SELECT session_id, snapshot_json, updated_at FROM snapshots"
        ).fetchall()
        for session_id, snapshot_json, updated_at in rows:
            client_id = ""
            try:
                payload = json.loads(snapshot_json)
                client_id = self._normalize_client_id(payload.get("client_id"))
            except Exception:
                client_id = ""

            conn.execute(
                """
                INSERT OR REPLACE INTO snapshots_v2
                (client_id, session_id, snapshot_json, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (client_id, session_id, snapshot_json, updated_at),
            )

        conn.execute("DROP TABLE snapshots")
        conn.execute("ALTER TABLE snapshots_v2 RENAME TO snapshots")
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_snapshots_session_id
            ON snapshots(session_id)
            """
        )

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            with conn:
                if not self._snapshots_table_exists(conn):
                    self._create_snapshots_table(conn)
                elif not self._snapshots_has_client_id_column(conn):
                    self._migrate_legacy_snapshots_table(conn)
                else:
                    self._create_snapshots_table(conn)

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS locks (
                        name TEXT PRIMARY KEY,
                        locked_at REAL NOT NULL,
                        expires_at REAL NOT NULL
                    )
                    """
                )
        finally:
            conn.close()

    def enqueue(
        self,
        session_id: str,
        snapshot: Dict[str, Any],
        client_id: Optional[str] = None,
    ) -> None:
        """Insert or replace snapshot in buffer."""
        effective_client_id = self._normalize_client_id(
            client_id if client_id is not None else snapshot.get("client_id")
        )
        payload = json.dumps(snapshot)
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO snapshots
                    (client_id, session_id, snapshot_json, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (effective_client_id, session_id, payload, time.time()),
                )
        finally:
            conn.close()

    def get(self, session_id: str, client_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Fetch snapshot by session_id and optionally client_id."""
        conn = self._connect()
        try:
            if client_id is not None:
                norm_client_id = self._normalize_client_id(client_id)
                cur = conn.execute(
                    """
                    SELECT snapshot_json
                    FROM snapshots
                    WHERE session_id = ? AND client_id = ?
                    """,
                    (session_id, norm_client_id),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return json.loads(row[0])

            rows = conn.execute(
                """
                SELECT client_id, snapshot_json
                FROM snapshots
                WHERE session_id = ?
                ORDER BY updated_at DESC
                """,
                (session_id,),
            ).fetchall()
            if not rows:
                return None
            if len(rows) > 1:
                logger.warning(
                    "Multiple snapshots found for session without client_id; ambiguous lookup rejected",
                    session_id=session_id,
                    matches=len(rows),
                )
                return None
            return json.loads(rows[0][1])
        finally:
            conn.close()

    def delete(self, session_id: str, client_id: Optional[str] = None) -> None:
        """Delete snapshot by session_id and optionally client_id."""
        conn = self._connect()
        try:
            with conn:
                if client_id is None:
                    conn.execute(
                        "DELETE FROM snapshots WHERE session_id = ?",
                        (session_id,),
                    )
                else:
                    norm_client_id = self._normalize_client_id(client_id)
                    conn.execute(
                        """
                        DELETE FROM snapshots
                        WHERE session_id = ? AND client_id = ?
                        """,
                        (session_id, norm_client_id),
                    )
        finally:
            conn.close()

    def get_all(self) -> Dict[str, Dict[str, Any]]:
        """Fetch all snapshots keyed by tenant-aware storage key."""
        conn = self._connect()
        try:
            cur = conn.execute(
                """
                SELECT client_id, session_id, snapshot_json
                FROM snapshots
                ORDER BY updated_at ASC
                """
            )
            result = {}
            for client_id, session_id, payload in cur.fetchall():
                result[self._storage_key(session_id, client_id)] = json.loads(payload)
            return result
        finally:
            conn.close()

    def get_all_entries(self) -> List[Dict[str, Any]]:
        """Fetch all snapshots with explicit (client_id, session_id)."""
        conn = self._connect()
        try:
            cur = conn.execute(
                """
                SELECT client_id, session_id, snapshot_json
                FROM snapshots
                ORDER BY updated_at ASC
                """
            )
            entries: List[Dict[str, Any]] = []
            for client_id, session_id, payload in cur.fetchall():
                entries.append(
                    {
                        "client_id": client_id or None,
                        "session_id": session_id,
                        "snapshot": json.loads(payload),
                    }
                )
            return entries
        finally:
            conn.close()

    def clear(self) -> None:
        """Remove all snapshots."""
        conn = self._connect()
        try:
            with conn:
                conn.execute("DELETE FROM snapshots")
        finally:
            conn.close()

    def count(self) -> int:
        """Count pending snapshots."""
        conn = self._connect()
        try:
            cur = conn.execute("SELECT COUNT(*) FROM snapshots")
            row = cur.fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()

    @property
    def last_flush_date(self) -> Optional[tuple]:
        """Return last flush date as (year, month, day) or None."""
        value = self._get_meta("last_flush_date")
        if not value:
            return None
        try:
            parts = [int(p) for p in value.split("-")]
            if len(parts) == 3:
                return (parts[0], parts[1], parts[2])
        except ValueError:
            return None
        return None

    @last_flush_date.setter
    def last_flush_date(self, value: Optional[tuple]) -> None:
        if value is None:
            self._set_meta("last_flush_date", None)
            return
        if isinstance(value, tuple) and len(value) == 3:
            formatted = f"{value[0]:04d}-{value[1]:02d}-{value[2]:02d}"
        else:
            formatted = str(value)
        self._set_meta("last_flush_date", formatted)

    def _get_meta(self, key: str) -> Optional[str]:
        conn = self._connect()
        try:
            cur = conn.execute("SELECT value FROM metadata WHERE key = ?", (key,))
            row = cur.fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def _set_meta(self, key: str, value: Optional[str]) -> None:
        conn = self._connect()
        try:
            with conn:
                if value is None:
                    conn.execute("DELETE FROM metadata WHERE key = ?", (key,))
                else:
                    conn.execute(
                        "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                        (key, value),
                    )
        finally:
            conn.close()

    def try_flush_lock(self, ttl_seconds: int = 600) -> bool:
        """Try to acquire flush lock. Returns True if acquired."""
        now = time.time()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT expires_at FROM locks WHERE name = ?",
                (self.LOCK_NAME,),
            ).fetchone()
            if row and row[0] > now:
                conn.execute("ROLLBACK")
                return False

            conn.execute(
                """
                INSERT OR REPLACE INTO locks (name, locked_at, expires_at)
                VALUES (?, ?, ?)
                """,
                (self.LOCK_NAME, now, now + ttl_seconds),
            )
            conn.commit()
            return True
        except Exception as exc:
            logger.warning("Failed to acquire snapshot flush lock", error=str(exc))
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            return False
        finally:
            conn.close()

    def release_flush_lock(self) -> None:
        """Release flush lock."""
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    "DELETE FROM locks WHERE name = ?",
                    (self.LOCK_NAME,),
                )
        finally:
            conn.close()
