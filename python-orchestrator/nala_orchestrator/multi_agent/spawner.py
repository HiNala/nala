"""Worker agent spawner.

Creates worker agent instances that run as asyncio tasks, each with
their own LLM session, scoped context, and tool permissions.

Workers report their results through the shared task list, not directly
to the lead — keeping coordination decoupled (open-multi-agent pattern).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nala_orchestrator.chunking.embedder import Embedder
    from nala_orchestrator.config import Config
    from nala_orchestrator.models.router import ModelRouter

from .file_locks import FileLockRegistry
from .messages import MessageBus
from .task_list import SharedTaskList, Task

log = logging.getLogger(__name__)

# Hard wall on how long a single worker task may run before being cancelled.
_WORKER_TIMEOUT = 300  # seconds


@dataclass
class WorkerResult:
    """The outcome reported by a worker agent."""
    task_id: str
    agent_id: str
    success: bool
    summary: str
    files_touched: list[str]


class WorkerAgent:
    """A scoped agent running one task in its own asyncio context."""

    def __init__(
        self,
        agent_id: str,
        task: Task,
        config: Config,
        task_list: SharedTaskList,
        locks: FileLockRegistry,
        bus: MessageBus,
        project_root: Path | None = None,
        embedder: Embedder | None = None,
        project_brief: str = "",
        model_override: tuple[str, str] | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.task = task
        self.config = config
        self._task_list = task_list
        self._locks = locks
        self._bus = bus
        self._project_root = project_root
        self._embedder = embedder
        self._project_brief = project_brief
        self._model_override = model_override

    async def run(self) -> WorkerResult:
        """Execute the task and report back through the task list."""
        # Acquire file locks for scoped files
        acquired: list[str] = []
        for fp in self.task.scope:
            if not self._locks.acquire(self.agent_id, fp):
                holder = self._locks.holder(fp)
                log.warning("Agent %s: file %s locked by %s", self.agent_id, fp, holder)
            else:
                acquired.append(fp)

        from ..agents.launcher import spawn_registered_worker
        from ..agents.registry import AgentRegistry

        project_root = self._project_root or Path(".")
        registry = AgentRegistry(project_root)
        spawn_registered_worker(project_root, self.agent_id, self.task.id)

        # Poll until the task finishes or the process dies (or timeout)
        import time
        start_time = time.time()
        while time.time() - start_time < _WORKER_TIMEOUT:
            # Exit early if the task already reached a terminal state
            task_check = self._task_list.get_task(self.task.id)
            if task_check and task_check.status.value in ("completed", "failed"):
                break
            # Exit if the process is gone (crashed or finished without updating task)
            if not registry.is_alive(self.agent_id):
                break
            await asyncio.sleep(2)
            
        # Post exit status check
        task = self._task_list.get_task(self.task.id)
        if task and task.status.value in ("completed", "failed"):
            success = task.status.value == "completed"
            summary = task.result_summary
        else:
            success = False
            summary = "Agent crashed or terminated without updating task."
            self._task_list.fail_task(self.agent_id, self.task.id, summary)

        registry.cleanup_dead()

        for fp in acquired:
            self._locks.release(self.agent_id, fp)

        return WorkerResult(
            task_id=self.task.id,
            agent_id=self.agent_id,
            success=success,
            summary=summary,
            files_touched=[],
        )



class AgentSpawner:
    """Spawns and runs worker agents for a task wave."""

    def __init__(
        self,
        config: Config,
        task_list: SharedTaskList,
        locks: FileLockRegistry,
        bus: MessageBus,
        max_concurrent: int = 3,
        model_router: ModelRouter | None = None,
        project_root: Path | None = None,
        embedder: Embedder | None = None,
        project_brief: str = "",
    ) -> None:
        self._config = config
        self._task_list = task_list
        self._locks = locks
        self._bus = bus
        self._max_concurrent = max_concurrent
        self._router = model_router
        self._project_root = project_root
        self._embedder = embedder
        self._project_brief = project_brief
        self._agent_counter = 0

    def set_embedder(self, embedder: Embedder) -> None:
        """Update the embedder reference (called after index rebuild)."""
        self._embedder = embedder

    def _resolve_model(self) -> tuple[str, str] | None:
        """Use the router to pick a coding model for workers."""
        if self._router is None:
            return None
        try:
            from nala_orchestrator.models.types import TaskType
            result = self._router.route(TaskType.CODE)
            return (result.provider.value, result.model_id)
        except Exception:
            return None

    async def run_wave(self, tasks: list[Task]) -> list[WorkerResult]:
        """Run a list of tasks in parallel up to max_concurrent."""
        semaphore = asyncio.Semaphore(self._max_concurrent)
        model_override = self._resolve_model()

        async def run_one(task: Task) -> WorkerResult:
            self._agent_counter += 1
            agent_id = f"worker-{self._agent_counter}"
            worker = WorkerAgent(
                agent_id=agent_id,
                task=task,
                config=self._config,
                task_list=self._task_list,
                locks=self._locks,
                bus=self._bus,
                project_root=self._project_root,
                embedder=self._embedder,
                project_brief=self._project_brief,
                model_override=model_override,
            )
            async with semaphore:
                log.info(
                    "Worker %s starting task: %s (model: %s)",
                    agent_id,
                    task.objective[:50],
                    f"{model_override[0]}/{model_override[1]}" if model_override else "default",
                )
                result = await worker.run()
                log.info(
                    "Worker %s finished: %s (%s)",
                    agent_id, "OK" if result.success else "FAIL", task.id,
                )
                return result

        aws = [run_one(t) for t in tasks]
        results = list(await asyncio.gather(*aws, return_exceptions=False))
        return results
