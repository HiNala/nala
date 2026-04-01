"""Lead agent orchestrator.

The LeadAgent:
  1. Receives a high-level objective from the user
  2. Uses TaskDecomposer to create a TaskPlan
  3. Optionally presents the plan for user approval
  4. Spawns worker agents in waves via AgentSpawner
  5. Monitors the SharedTaskList for progress
  6. Handles failures (retry / escalate)
  7. Synthesises a final summary from worker results

Inspired by open-multi-agent's event-driven coordination pattern:
  - No polling — waves complete before the next starts
  - Central task list as single source of truth
  - Workers communicate discoveries via MessageBus
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from nala_orchestrator.config import Config

from .task_list import SharedTaskList, TaskStatus
from .file_locks import FileLockRegistry
from .messages import MessageBus
from .spawner import AgentSpawner, WorkerResult
from .decomposer import TaskDecomposer, TaskPlan

log = logging.getLogger(__name__)


@dataclass
class TeamStatus:
    """Current status of an agent team run."""
    objective: str
    plan: Optional[TaskPlan] = None
    current_wave: int = 0
    completed_tasks: int = 0
    total_tasks: int = 0
    results: list[WorkerResult] = field(default_factory=list)
    final_summary: str = ""
    is_running: bool = False
    error: str = ""

    def format_progress(self) -> str:
        if not self.plan:
            return "No plan yet."
        lines = [f"Agent Team: {self.objective[:60]}"]
        task_list_fmt = []
        for wave in self.plan.waves:
            for t in wave:
                task_list_fmt.append(f"  - {t.title}")
        lines += task_list_fmt
        lines.append(f"\n  Tasks: {self.completed_tasks}/{self.total_tasks} completed")
        return "\n".join(lines)


class LeadAgent:
    """Orchestrates a team of worker agents for a complex objective."""

    def __init__(self, config: "Config", project_root: Path) -> None:
        self._config = config
        self._root = project_root
        self._task_list = SharedTaskList(project_root)
        self._locks = FileLockRegistry()
        self._bus = MessageBus()
        self._spawner = AgentSpawner(
            config=config,
            task_list=self._task_list,
            locks=self._locks,
            bus=self._bus,
            max_concurrent=3,
        )
        self._status = TeamStatus(objective="")

    # ── Public API ────────────────────────────────────────────────────────────

    async def run(self, objective: str) -> TeamStatus:
        """Decompose and execute a full multi-agent run."""
        self._task_list.clear()
        self._locks = FileLockRegistry()  # fresh locks
        self._bus.clear()
        self._status = TeamStatus(objective=objective, is_running=True)

        try:
            decomposer = TaskDecomposer(self._root)
            plan = decomposer.decompose(objective)
            self._status.plan = plan
            self._status.total_tasks = len(plan.all_tasks)
            log.info("Task plan:\n%s", plan.summary())

            for wave_idx, wave_tasks in enumerate(plan.waves):
                self._status.current_wave = wave_idx
                log.info("Starting wave %d (%d tasks)", wave_idx + 1, len(wave_tasks))

                # Register tasks in the task list
                task_objs = []
                for sub in wave_tasks:
                    task_objs.append(
                        self._task_list.add_task(
                            objective=sub.objective,
                            assigned_to="",  # any available worker
                            scope=sub.scope,
                            dependencies=[],  # wave ordering handles deps
                        )
                    )

                # Execute wave in parallel
                results = await self._spawner.run_wave(task_objs)
                self._status.results.extend(results)
                self._status.completed_tasks += len(results)

                # Broadcast any key findings to subsequent waves
                findings = [r.summary for r in results if r.success and r.summary]
                if findings:
                    self._bus.broadcast(
                        "lead",
                        "Previous wave findings: " + " | ".join(f[:100] for f in findings),
                    )

            self._status.final_summary = self._synthesise()
        except Exception as e:
            self._status.error = str(e)
            log.exception("LeadAgent run failed: %s", e)
        finally:
            self._status.is_running = False

        return self._status

    async def stream_run(self, objective: str) -> AsyncIterator[str]:
        """Stream progress updates while running a team."""
        yield f"Planning: {objective}\n"
        decomposer = TaskDecomposer(self._root)
        plan = decomposer.decompose(objective)
        yield plan.summary() + "\n\n"

        status = await self.run(objective)
        yield status.final_summary

    def get_status(self) -> str:
        """Return current team status as a formatted string."""
        if not self._status.plan:
            return "No team run active."
        ts = self._task_list.status_summary()
        locks = self._locks.format_status()
        return f"{self._status.format_progress()}\n\n{ts}\n\n{locks}"

    # ── Internal ──────────────────────────────────────────────────────────────

    def _synthesise(self) -> str:
        """Merge worker results into a final summary."""
        results = self._status.results
        if not results:
            return "No results from worker agents."
        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]
        lines = [
            f"Team run complete: {len(successes)}/{len(results)} tasks succeeded.",
            "",
        ]
        if successes:
            lines.append("Results:")
            for r in successes:
                lines.append(f"  [{r.agent_id}] {r.summary[:150]}")
        if failures:
            lines.append("\nFailed tasks:")
            for r in failures:
                lines.append(f"  [{r.agent_id}] {r.summary[:100]}")
        return "\n".join(lines)
