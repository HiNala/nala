"""Shared task list backed by SQLite.

Provides a dependency-aware task queue that multiple agents can claim,
complete, or block.  Dependencies are resolved automatically: a task
becomes pending only when all of its dependencies are completed.
"""

from __future__ import annotations

import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

log = logging.getLogger(__name__)

_DB_PATH = ".nala/multi_agent/tasks.db"


class TaskStatus(str, Enum):
    PENDING    = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED  = "completed"
    BLOCKED    = "blocked"
    FAILED     = "failed"


@dataclass
class Task:
    """A unit of work assignable to one agent."""
    id: str
    objective: str
    assigned_to: str = ""
    status: TaskStatus = TaskStatus.PENDING
    scope: list[str] = field(default_factory=list)        # file paths
    dependencies: list[str] = field(default_factory=list) # task IDs
    result_summary: str = ""
    created_at: float = field(default_factory=time.time)
    completed_at: float = 0.0


class SharedTaskList:
    """Persistent task queue with dependency resolution."""

    def __init__(self, project_root: Path) -> None:
        db_path = project_root / _DB_PATH
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._init_schema()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                objective TEXT NOT NULL,
                assigned_to TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                scope TEXT DEFAULT '[]',
                dependencies TEXT DEFAULT '[]',
                result_summary TEXT DEFAULT '',
                created_at REAL DEFAULT 0,
                completed_at REAL DEFAULT 0
            );
        """)
        self._conn.commit()

    # ── Mutation ──────────────────────────────────────────────────────────────

    def add_task(
        self,
        objective: str,
        assigned_to: str = "",
        scope: list[str] | None = None,
        dependencies: list[str] | None = None,
    ) -> Task:
        """Add a new task and determine its initial status."""
        import json
        task_id = str(uuid.uuid4())[:8]
        deps = dependencies or []
        initial_status = self._resolve_initial_status(deps)
        task = Task(
            id=task_id,
            objective=objective,
            assigned_to=assigned_to,
            status=initial_status,
            scope=scope or [],
            dependencies=deps,
            created_at=time.time(),
        )
        self._conn.execute(
            "INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?)",
            (task_id, objective, assigned_to, initial_status.value,
             json.dumps(scope or []), json.dumps(deps), "", time.time(), 0.0),
        )
        self._conn.commit()
        log.debug("Task added: %s [%s] → %s", task_id, initial_status.value, objective[:50])
        return task

    def claim_task(self, agent_id: str, task_id: str) -> bool:
        """Mark a task as in_progress for an agent. Returns False if already taken."""
        cur = self._conn.execute(
            "UPDATE tasks SET status=?, assigned_to=? WHERE id=? AND status=?",
            (TaskStatus.IN_PROGRESS.value, agent_id, task_id, TaskStatus.PENDING.value),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def complete_task(self, agent_id: str, task_id: str, result: str = "") -> None:
        """Mark a task completed and unblock any dependent tasks."""
        self._conn.execute(
            "UPDATE tasks SET status=?, result_summary=?, completed_at=? "
            "WHERE id=? AND assigned_to=?",
            (TaskStatus.COMPLETED.value, result, time.time(), task_id, agent_id),
        )
        self._conn.commit()
        self._unblock_dependents(task_id)

    def fail_task(self, agent_id: str, task_id: str, reason: str = "") -> None:
        """Mark a task failed and cascade-fail dependents."""
        self._conn.execute(
            "UPDATE tasks SET status=?, result_summary=? WHERE id=?",
            (TaskStatus.FAILED.value, reason, task_id),
        )
        self._conn.commit()
        self._cascade_fail(task_id)

    def block_task(self, agent_id: str, task_id: str, reason: str = "") -> None:
        """Mark a task blocked (dependency or external)."""
        self._conn.execute(
            "UPDATE tasks SET status=?, result_summary=? WHERE id=?",
            (TaskStatus.BLOCKED.value, reason, task_id),
        )
        self._conn.commit()

    # ── Query ─────────────────────────────────────────────────────────────────

    def get_available_tasks(self, agent_id: str = "") -> list[Task]:
        """Return pending tasks whose dependencies are all completed."""
        rows = self._conn.execute(
            "SELECT * FROM tasks WHERE status=?",
            (TaskStatus.PENDING.value,),
        ).fetchall()
        available: list[Task] = []
        for row in rows:
            task = self._row_to_task(row)
            if agent_id and task.assigned_to and task.assigned_to != agent_id:
                continue
            available.append(task)
        return available

    def get_all_tasks(self) -> list[Task]:
        rows = self._conn.execute("SELECT * FROM tasks ORDER BY created_at").fetchall()
        return [self._row_to_task(r) for r in rows]

    def get_task(self, task_id: str) -> Task | None:
        row = self._conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return self._row_to_task(row) if row else None

    def status_summary(self) -> str:
        """Return a human-readable status summary for the TUI."""
        all_tasks = self.get_all_tasks()
        counts: dict[str, int] = {}
        for t in all_tasks:
            counts[t.status.value] = counts.get(t.status.value, 0) + 1
        total = len(all_tasks)
        done = counts.get("completed", 0)
        in_prog = counts.get("in_progress", 0)
        pending = counts.get("pending", 0)
        return f"Tasks: {done}/{total} completed | {in_prog} in progress | {pending} pending"

    def clear(self) -> None:
        """Remove all tasks (used between team runs)."""
        self._conn.execute("DELETE FROM tasks")
        self._conn.commit()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _resolve_initial_status(self, deps: list[str]) -> TaskStatus:
        if not deps:
            return TaskStatus.PENDING
        # Check if all deps are completed
        for dep_id in deps:
            row = self._conn.execute(
                "SELECT status FROM tasks WHERE id=?", (dep_id,)
            ).fetchone()
            if row is None or row[0] != TaskStatus.COMPLETED.value:
                return TaskStatus.BLOCKED
        return TaskStatus.PENDING

    def _unblock_dependents(self, completed_id: str) -> None:
        """After a task completes, promote any blocked dependents to pending."""
        import json
        blocked = self._conn.execute(
            "SELECT id, dependencies FROM tasks WHERE status=?",
            (TaskStatus.BLOCKED.value,),
        ).fetchall()
        for row in blocked:
            task_id = row[0]
            deps = json.loads(row[1] or "[]")
            if completed_id not in deps:
                continue
            # Check if all deps are now complete
            all_done = all(
                self._conn.execute(
                    "SELECT status FROM tasks WHERE id=?", (d,)
                ).fetchone()[0] == TaskStatus.COMPLETED.value
                for d in deps
                if d != completed_id
            )
            if all_done:
                self._conn.execute(
                    "UPDATE tasks SET status=? WHERE id=?",
                    (TaskStatus.PENDING.value, task_id),
                )
        self._conn.commit()

    def _cascade_fail(self, failed_id: str) -> None:
        """Transitively fail tasks that depend on a failed task."""
        import json
        all_tasks = self._conn.execute(
            "SELECT id, dependencies FROM tasks WHERE status NOT IN (?,?)",
            (TaskStatus.COMPLETED.value, TaskStatus.FAILED.value),
        ).fetchall()
        for row in all_tasks:
            task_id, deps_json = row
            deps = json.loads(deps_json or "[]")
            if failed_id in deps:
                self._conn.execute(
                    "UPDATE tasks SET status=?, result_summary=? WHERE id=?",
                    (TaskStatus.FAILED.value, f"Dependency {failed_id} failed", task_id),
                )
                self._cascade_fail(task_id)
        self._conn.commit()

    @staticmethod
    def _row_to_task(row: tuple) -> Task:
        import json
        return Task(
            id=row[0],
            objective=row[1],
            assigned_to=row[2],
            status=TaskStatus(row[3]),
            scope=json.loads(row[4] or "[]"),
            dependencies=json.loads(row[5] or "[]"),
            result_summary=row[6],
            created_at=row[7],
            completed_at=row[8],
        )
