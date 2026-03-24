"""
SessionLockManager - cross-process locks for session_id handling.

Default implementation uses filesystem locks (fcntl).
"""

from __future__ import annotations

import hashlib
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

import fcntl


class SessionLockManager:
    """Acquire per-session locks across processes."""

    def __init__(self, lock_dir: Optional[str] = None):
        self._lock_dir = Path(
            lock_dir or os.getenv("SESSION_LOCK_DIR", "/tmp/crm_sales_bot_session_locks")
        ).resolve()
        self._lock_dir.mkdir(parents=True, exist_ok=True)
        self._local_locks: dict[str, threading.RLock] = {}
        self._local_locks_guard = threading.Lock()

    def _get_local_lock(self, session_id: str) -> threading.RLock:
        with self._local_locks_guard:
            lock = self._local_locks.get(session_id)
            if lock is None:
                lock = threading.RLock()
                self._local_locks[session_id] = lock
            return lock

    def _lock_path(self, session_id: str) -> Path:
        digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
        return self._lock_dir / f"{digest}.lock"

    @contextmanager
    def lock(self, session_id: str) -> Iterator[None]:
        """Context manager for session lock."""
        path = self._lock_path(session_id)
        local_lock = self._get_local_lock(session_id)
        with local_lock:
            with open(path, "a", encoding="utf-8") as handle:
                fcntl.flock(handle, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle, fcntl.LOCK_UN)
