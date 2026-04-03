"""Worker registry — tracks spawned agent workers for the orchestrator.

Each worker is a bounded sub-agent with a named role, scoped objective,
and a parent run ID linking it back to the orchestrator session.

Design rules (Mission 32):
  - Max 3 workers per orchestrator run
  - Workers cannot recursively spawn more workers
  - The interpreter terminal receives compressed summaries, not raw logs
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

log = logging.getLogger("nala.agent_runtime.workers")

MAX_WORKERS = 3  # default; overridden by settings via set_max_workers()


class WorkerRole(str, Enum):
    RESEARCH = "research"
    IMPLEMENT = "implement"
    VERIFY = "verify"
    EXPLORE = "explore"
    EDIT = "edit"
    REVIEW = "review"


class WorkerStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class WorkerInfo:
    """Metadata for a single spawned worker."""
    worker_id: str = field(default_factory=lambda: f"w-{uuid.uuid4().hex[:8]}")
    label: str = ""
    role: WorkerRole = WorkerRole.IMPLEMENT
    objective: str = ""
    scope: str = ""
    status: WorkerStatus = WorkerStatus.PENDING
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str = ""
    parent_run_id: str = ""
    result_summary: str = ""
    files_touched: list[str] = field(default_factory=list)
    worktree_path: str = ""

    def to_dict(self) -> dict:
        return {
            "worker_id": self.worker_id,
            "label": self.label,
            "role": self.role.value,
            "objective": self.objective,
            "scope": self.scope,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "parent_run_id": self.parent_run_id,
            "result_summary": self.result_summary,
            "files_touched": self.files_touched,
            "worktree_path": self.worktree_path,
        }

    @classmethod
    def from_dict(cls, d: dict) -> WorkerInfo:
        d = dict(d)
        d["role"] = WorkerRole(d.get("role", "implement"))
        d["status"] = WorkerStatus(d.get("status", "pending"))
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def status_line(self) -> str:
        icon = {
            WorkerStatus.PENDING: "◌",
            WorkerStatus.RUNNING: "●",
            WorkerStatus.BLOCKED: "⚠",
            WorkerStatus.COMPLETED: "✓",
            WorkerStatus.FAILED: "✗",
            WorkerStatus.CANCELLED: "○",
        }.get(self.status, "?")
        return f"{icon} [{self.worker_id}] {self.role.value}: {self.label or self.objective[:40]}"


class WorkerRegistry:
    """Tracks active workers for one orchestrator run."""

    def __init__(self, parent_run_id: str = "", max_workers: int = 0) -> None:
        self._workers: dict[str, WorkerInfo] = {}
        self._parent_run_id = parent_run_id
        self._max_workers = max_workers if max_workers > 0 else MAX_WORKERS

    def set_max_workers(self, n: int) -> None:
        if n > 0:
            self._max_workers = n

    @property
    def count(self) -> int:
        return len(self._workers)

    @property
    def active_count(self) -> int:
        return sum(
            1 for w in self._workers.values()
            if w.status in (WorkerStatus.PENDING, WorkerStatus.RUNNING)
        )

    def can_spawn(self) -> bool:
        return self.active_count < self._max_workers

    def spawn(
        self,
        objective: str,
        role: WorkerRole = WorkerRole.IMPLEMENT,
        scope: str = "",
        label: str = "",
        worktree_path: str = "",
    ) -> WorkerInfo | None:
        """Register a new worker. Returns None if limit reached."""
        if not self.can_spawn():
            log.warning("Worker limit reached (%d/%d)", self.active_count, self._max_workers)
            return None
        worker = WorkerInfo(
            label=label or objective[:30],
            role=role,
            objective=objective,
            scope=scope,
            parent_run_id=self._parent_run_id,
            worktree_path=worktree_path,
        )
        self._workers[worker.worker_id] = worker
        log.info("Spawned worker %s (%s): %s", worker.worker_id, role.value, objective[:60])
        return worker

    def get(self, worker_id: str) -> WorkerInfo | None:
        return self._workers.get(worker_id)

    def list_all(self) -> list[WorkerInfo]:
        return list(self._workers.values())

    def list_active(self) -> list[WorkerInfo]:
        return [
            w for w in self._workers.values()
            if w.status in (WorkerStatus.PENDING, WorkerStatus.RUNNING)
        ]

    def update_status(self, worker_id: str, status: WorkerStatus, summary: str = "") -> None:
        worker = self._workers.get(worker_id)
        if worker is None:
            return
        worker.status = status
        if summary:
            worker.result_summary = summary
        if status in (WorkerStatus.COMPLETED, WorkerStatus.FAILED, WorkerStatus.CANCELLED):
            worker.completed_at = datetime.now(UTC).isoformat()

    def cancel(self, worker_id: str) -> bool:
        worker = self._workers.get(worker_id)
        if worker is None:
            return False
        if worker.status in (WorkerStatus.PENDING, WorkerStatus.RUNNING):
            worker.status = WorkerStatus.CANCELLED
            worker.completed_at = datetime.now(UTC).isoformat()
            return True
        return False

    def cancel_all(self) -> int:
        count = 0
        for w in self._workers.values():
            if w.status in (WorkerStatus.PENDING, WorkerStatus.RUNNING):
                w.status = WorkerStatus.CANCELLED
                w.completed_at = datetime.now(UTC).isoformat()
                count += 1
        return count

    def format_summary(self) -> str:
        if not self._workers:
            return "No workers spawned."
        lines = [f"**Workers** ({self.active_count} active / {self.count} total)"]
        for w in self._workers.values():
            lines.append(f"  {w.status_line()}")
        return "\n".join(lines)

    def to_list(self) -> list[dict]:
        return [w.to_dict() for w in self._workers.values()]

    @classmethod
    def from_list(cls, data: list[dict], parent_run_id: str = "") -> WorkerRegistry:
        reg = cls(parent_run_id)
        for d in data:
            info = WorkerInfo.from_dict(d)
            reg._workers[info.worker_id] = info
        return reg
