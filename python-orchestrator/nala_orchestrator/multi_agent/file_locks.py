"""File lock registry.

Prevents two agents from modifying the same file concurrently.
Locks auto-expire after 5 minutes of inactivity to prevent deadlocks
from crashed agents.
"""

from __future__ import annotations

import time
from threading import Lock

_LOCK_TTL_SECONDS = 300  # 5 minutes


class FileLockRegistry:
    """Thread-safe file lock registry with TTL-based expiry."""

    def __init__(self) -> None:
        self._locks: dict[str, tuple[str, float]] = {}  # path → (agent_id, acquired_at)
        self._mutex = Lock()

    def acquire(self, agent_id: str, file_path: str) -> bool:
        """Acquire a lock on file_path for agent_id.

        Returns True if acquired, False if already locked by another agent.
        Expired locks are cleared automatically.
        """
        with self._mutex:
            self._expire_stale()
            if file_path in self._locks:
                holder, _ = self._locks[file_path]
                if holder != agent_id:
                    return False
            self._locks[file_path] = (agent_id, time.time())
            return True

    def release(self, agent_id: str, file_path: str) -> bool:
        """Release a lock held by agent_id. Returns False if not held."""
        with self._mutex:
            entry = self._locks.get(file_path)
            if entry is None or entry[0] != agent_id:
                return False
            del self._locks[file_path]
            return True

    def release_all(self, agent_id: str) -> int:
        """Release all locks held by an agent. Returns count released."""
        with self._mutex:
            to_remove = [p for p, (aid, _) in self._locks.items() if aid == agent_id]
            for p in to_remove:
                del self._locks[p]
            return len(to_remove)

    def get_locks(self) -> dict[str, str]:
        """Return {file_path: agent_id} for all active locks."""
        with self._mutex:
            self._expire_stale()
            return {p: aid for p, (aid, _) in self._locks.items()}

    def is_locked(self, file_path: str) -> bool:
        with self._mutex:
            self._expire_stale()
            return file_path in self._locks

    def holder(self, file_path: str) -> str:
        """Return the agent_id holding the lock, or empty string."""
        with self._mutex:
            entry = self._locks.get(file_path)
            return entry[0] if entry else ""

    def format_status(self) -> str:
        locked = self.get_locks()
        if not locked:
            return "No files locked."
        lines = [f"  {path} → {aid}" for path, aid in sorted(locked.items())]
        return "Locked files:\n" + "\n".join(lines)

    def _expire_stale(self) -> None:
        now = time.time()
        expired = [p for p, (_, t) in self._locks.items()
                   if now - t > _LOCK_TTL_SECONDS]
        for p in expired:
            del self._locks[p]
