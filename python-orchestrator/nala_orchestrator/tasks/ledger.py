"""Task ledger: structured task objects for resumability and handoff.

Every agent run creates task objects with objective, constraints, files in
scope, plan, status, and artifacts.  Tasks are persisted inside the session
directory so they survive restarts and feed into handoff documents.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path


class TaskStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"


@dataclass
class Task:
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    objective: str = ""
    constraints: list[str] = field(default_factory=list)
    files_in_scope: list[str] = field(default_factory=list)
    plan: list[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.OPEN
    blocked_on: str = ""
    tests_run: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str = ""
    summary: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Task:
        d = dict(d)
        if "status" in d:
            d["status"] = TaskStatus(d["status"])
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_markdown(self) -> str:
        lines = [
            f"## Task {self.task_id}: {self.objective}",
            f"**Status:** {self.status.value}",
        ]
        if self.plan:
            lines.append("**Plan:**")
            for i, step in enumerate(self.plan, 1):
                lines.append(f"  {i}. {step}")
        if self.files_in_scope:
            lines.append(f"**Files:** {', '.join(self.files_in_scope)}")
        if self.constraints:
            lines.append(f"**Constraints:** {', '.join(self.constraints)}")
        if self.blocked_on:
            lines.append(f"**Blocked on:** {self.blocked_on}")
        if self.tests_run:
            lines.append(f"**Tests run:** {', '.join(self.tests_run)}")
        if self.artifacts:
            lines.append(f"**Artifacts:** {', '.join(self.artifacts)}")
        if self.summary:
            lines.append(f"**Summary:** {self.summary}")
        return "\n".join(lines)


class TaskLedger:
    """Manages a list of tasks for the current session."""

    def __init__(self, sessions_dir: Path | None = None) -> None:
        self._tasks: list[Task] = []
        self._current_id: str | None = None
        self._storage_path: Path | None = None
        if sessions_dir:
            self._storage_path = sessions_dir / "tasks.json"
            self._load()

    def _load(self) -> None:
        if self._storage_path and self._storage_path.exists():
            try:
                data = json.loads(self._storage_path.read_text(encoding="utf-8"))
                self._tasks = [Task.from_dict(t) for t in data.get("tasks", [])]
                self._current_id = data.get("current_id")
            except (json.JSONDecodeError, KeyError):
                pass

    def _save(self) -> None:
        if self._storage_path:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "tasks": [t.to_dict() for t in self._tasks],
                "current_id": self._current_id,
            }
            self._storage_path.write_text(
                json.dumps(data, indent=2), encoding="utf-8"
            )

    def create_task(self, objective: str) -> Task:
        task = Task(objective=objective, status=TaskStatus.IN_PROGRESS)
        self._tasks.append(task)
        self._current_id = task.task_id
        self._save()
        return task

    def current_task(self) -> Task | None:
        if not self._current_id:
            return None
        return next((t for t in self._tasks if t.task_id == self._current_id), None)

    def complete_current(self, summary: str = "") -> Task | None:
        task = self.current_task()
        if task:
            task.status = TaskStatus.DONE
            task.completed_at = datetime.now(UTC).isoformat()
            task.summary = summary
            self._current_id = None
            self._save()
        return task

    def update_current(self, **kwargs) -> Task | None:
        task = self.current_task()
        if not task:
            return None
        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)
        self._save()
        return task

    def list_tasks(self) -> list[Task]:
        return list(self._tasks)

    def status_text(self) -> str:
        """Human-readable summary of the current task and recent tasks."""
        current = self.current_task()
        lines: list[str] = []

        if current:
            lines.append(f"Current task [{current.task_id}]: {current.objective}")
            lines.append(f"  Status: {current.status.value}")
            if current.plan:
                lines.append("  Plan:")
                for i, step in enumerate(current.plan, 1):
                    lines.append(f"    {i}. {step}")
            if current.files_in_scope:
                lines.append(f"  Files: {', '.join(current.files_in_scope[:10])}")
        else:
            lines.append("No active task. Use /task <objective> to start one.")

        done_count = sum(1 for t in self._tasks if t.status == TaskStatus.DONE)
        active = (TaskStatus.OPEN, TaskStatus.IN_PROGRESS)
        open_count = sum(1 for t in self._tasks if t.status in active)
        if done_count or open_count:
            lines.append(f"\nSession tasks: {open_count} active, {done_count} completed")

        return "\n".join(lines)

    def for_handoff(self) -> list[dict]:
        """Return task summaries suitable for inclusion in a handoff document."""
        return [t.to_dict() for t in self._tasks if t.status != TaskStatus.CANCELLED]
